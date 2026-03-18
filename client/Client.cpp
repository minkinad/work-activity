#include "client.h"

#include <bcrypt.h>
#include <objbase.h>
#include <shellapi.h>
#include <wincrypt.h>
#include <winhttp.h>
#include <winsvc.h>
#include <ws2tcpip.h>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "ws2_32.lib")

namespace {

constexpr int kProtocolVersion = 2;
constexpr DWORD kLoopSleepMilliseconds = 1000;

SERVICE_STATUS_HANDLE g_serviceStatusHandle = NULL;
SERVICE_STATUS g_serviceStatus = {};
HANDLE g_serviceStopEvent = NULL;
ClientConfig g_serviceConfig;

std::string Trim(const std::string& value) {
    const size_t begin = value.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return "";
    }

    const size_t end = value.find_last_not_of(" \t\r\n");
    return value.substr(begin, end - begin + 1);
}

std::string ToLower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char symbol) {
        return static_cast<char>(std::tolower(symbol));
    });
    return value;
}

std::wstring Widen(const std::string& value) {
    if (value.empty()) {
        return L"";
    }

    const int size = MultiByteToWideChar(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), NULL, 0);
    std::wstring result(size, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), result.data(), size);
    return result;
}

std::string Narrow(const std::wstring& value) {
    if (value.empty()) {
        return "";
    }

    const int size = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), NULL, 0, NULL, NULL);
    std::string result(size, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), result.data(), size, NULL, NULL);
    return result;
}

bool ParseBool(const std::string& value) {
    const std::string normalized = ToLower(Trim(value));
    return normalized == "1" || normalized == "true" || normalized == "yes" || normalized == "on";
}

int ParseIntOrDefault(const std::string& value, int fallback) {
    try {
        return std::stoi(value);
    } catch (...) {
        return fallback;
    }
}

std::string JsonEscape(const std::string& value) {
    std::ostringstream stream;
    for (char symbol : value) {
        switch (symbol) {
            case '\\':
                stream << "\\\\";
                break;
            case '"':
                stream << "\\\"";
                break;
            case '\n':
                stream << "\\n";
                break;
            case '\r':
                stream << "\\r";
                break;
            case '\t':
                stream << "\\t";
                break;
            default:
                stream << symbol;
                break;
        }
    }
    return stream.str();
}

std::wstring GetExecutablePath() {
    std::wstring buffer(MAX_PATH, L'\0');
    DWORD length = GetModuleFileNameW(NULL, buffer.data(), static_cast<DWORD>(buffer.size()));
    while (length == buffer.size()) {
        buffer.resize(buffer.size() * 2);
        length = GetModuleFileNameW(NULL, buffer.data(), static_cast<DWORD>(buffer.size()));
    }
    buffer.resize(length);
    return buffer;
}

std::wstring GetExecutableDirectory() {
    const std::wstring path = GetExecutablePath();
    const size_t separator = path.find_last_of(L"\\/");
    return separator == std::wstring::npos ? L"." : path.substr(0, separator);
}

void WriteRegistryString(HKEY root, const std::wstring& subkey, const std::wstring& name, const std::wstring& value) {
    HKEY handle = NULL;
    if (RegCreateKeyExW(root, subkey.c_str(), 0, NULL, REG_OPTION_NON_VOLATILE, KEY_SET_VALUE, NULL, &handle, NULL) != ERROR_SUCCESS) {
        return;
    }

    const DWORD sizeInBytes = static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t));
    RegSetValueExW(handle, name.c_str(), 0, REG_SZ, reinterpret_cast<const BYTE*>(value.c_str()), sizeInBytes);
    RegCloseKey(handle);
}

class WinsockSession {
public:
    WinsockSession() {
        WSADATA wsaData;
        initialized_ = WSAStartup(MAKEWORD(2, 2), &wsaData) == 0;
    }

    ~WinsockSession() {
        if (initialized_) {
            WSACleanup();
        }
    }

    bool IsInitialized() const {
        return initialized_;
    }

private:
    bool initialized_ = false;
};

class WinHttpHandle {
public:
    explicit WinHttpHandle(HINTERNET handle = NULL) : handle_(handle) {}

    ~WinHttpHandle() {
        if (handle_ != NULL) {
            WinHttpCloseHandle(handle_);
        }
    }

    HINTERNET Get() const {
        return handle_;
    }

    bool IsValid() const {
        return handle_ != NULL;
    }

    WinHttpHandle(const WinHttpHandle&) = delete;
    WinHttpHandle& operator=(const WinHttpHandle&) = delete;

    WinHttpHandle(WinHttpHandle&& other) noexcept : handle_(other.handle_) {
        other.handle_ = NULL;
    }

    WinHttpHandle& operator=(WinHttpHandle&& other) noexcept {
        if (this != &other) {
            if (handle_ != NULL) {
                WinHttpCloseHandle(handle_);
            }
            handle_ = other.handle_;
            other.handle_ = NULL;
        }
        return *this;
    }

private:
    HINTERNET handle_ = NULL;
};

struct HttpResponse {
    DWORD statusCode = 0;
    std::string body;
};

struct QueuedCommand {
    long long id = 0;
    std::string commandType;
};

std::string ReadEnvironmentVariable(const char* name) {
    DWORD size = GetEnvironmentVariableA(name, NULL, 0);
    if (size == 0) {
        return "";
    }

    std::string value(size, '\0');
    const DWORD written = GetEnvironmentVariableA(name, value.data(), size);
    if (written == 0) {
        return "";
    }

    value.resize(written);
    return value;
}

std::string ReadComputerName() {
    char buffer[MAX_COMPUTERNAME_LENGTH + 1] = {};
    DWORD size = MAX_COMPUTERNAME_LENGTH + 1;
    if (!GetComputerNameA(buffer, &size)) {
        return "";
    }
    return std::string(buffer, size);
}

std::string ReadUserName() {
    char buffer[256] = {};
    DWORD size = static_cast<DWORD>(sizeof(buffer));
    if (!GetUserNameA(buffer, &size) || size == 0) {
        return "";
    }

    if (buffer[size - 1] == '\0') {
        --size;
    }
    return std::string(buffer, size);
}

std::string ResolveLocalIpAddress() {
    char hostName[256] = {};
    if (gethostname(hostName, sizeof(hostName)) == SOCKET_ERROR) {
        return "";
    }

    addrinfo hints = {};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo* result = NULL;
    if (getaddrinfo(hostName, NULL, &hints, &result) != 0) {
        return "";
    }

    std::string ipAddress;
    for (addrinfo* entry = result; entry != NULL; entry = entry->ai_next) {
        const sockaddr_in* ipv4 = reinterpret_cast<const sockaddr_in*>(entry->ai_addr);
        char buffer[INET_ADDRSTRLEN] = {};
        if (inet_ntop(AF_INET, &ipv4->sin_addr, buffer, sizeof(buffer)) != NULL) {
            if (std::string(buffer) != "127.0.0.1") {
                ipAddress = buffer;
                break;
            }
        }
    }

    freeaddrinfo(result);
    return ipAddress;
}

std::string MakeClientId(const ClientIdentity& identity) {
    std::string value = identity.domain + "-" + identity.machine + "-" + identity.user;
    std::replace(value.begin(), value.end(), ' ', '_');
    return value;
}

std::string GenerateNonce() {
    GUID guid;
    if (CoCreateGuid(&guid) != S_OK) {
        return GetUtcTimestamp();
    }

    wchar_t buffer[64] = {};
    StringFromGUID2(guid, buffer, 64);
    return Narrow(buffer);
}

std::string Base64Encode(const std::vector<unsigned char>& bytes) {
    if (bytes.empty()) {
        return "";
    }

    DWORD requiredSize = 0;
    if (!CryptBinaryToStringA(bytes.data(), static_cast<DWORD>(bytes.size()), CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, NULL, &requiredSize)) {
        throw std::runtime_error("CryptBinaryToStringA failed");
    }

    std::string output(requiredSize, '\0');
    if (!CryptBinaryToStringA(bytes.data(), static_cast<DWORD>(bytes.size()), CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, output.data(), &requiredSize)) {
        throw std::runtime_error("CryptBinaryToStringA failed");
    }

    if (!output.empty() && output.back() == '\0') {
        output.pop_back();
    }
    return output;
}

std::vector<unsigned char> ComputeHmacSha256(const std::string& key, const std::string& message) {
    BCRYPT_ALG_HANDLE algorithmHandle = NULL;
    BCRYPT_HASH_HANDLE hashHandle = NULL;
    DWORD objectLength = 0;
    DWORD hashLength = 0;
    DWORD bytesRead = 0;

    if (!BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&algorithmHandle, BCRYPT_SHA256_ALGORITHM, NULL, BCRYPT_ALG_HANDLE_HMAC_FLAG))) {
        throw std::runtime_error("BCryptOpenAlgorithmProvider failed");
    }

    std::vector<unsigned char> hashBytes;
    std::vector<unsigned char> objectBuffer;

    try {
        if (!BCRYPT_SUCCESS(BCryptGetProperty(algorithmHandle, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&objectLength), sizeof(objectLength), &bytesRead, 0))) {
            throw std::runtime_error("BCryptGetProperty(BCRYPT_OBJECT_LENGTH) failed");
        }

        if (!BCRYPT_SUCCESS(BCryptGetProperty(algorithmHandle, BCRYPT_HASH_LENGTH, reinterpret_cast<PUCHAR>(&hashLength), sizeof(hashLength), &bytesRead, 0))) {
            throw std::runtime_error("BCryptGetProperty(BCRYPT_HASH_LENGTH) failed");
        }

        objectBuffer.resize(objectLength);
        hashBytes.resize(hashLength);

        if (!BCRYPT_SUCCESS(BCryptCreateHash(
                algorithmHandle,
                &hashHandle,
                objectBuffer.data(),
                static_cast<ULONG>(objectBuffer.size()),
                reinterpret_cast<PUCHAR>(const_cast<char*>(key.data())),
                static_cast<ULONG>(key.size()),
                0))) {
            throw std::runtime_error("BCryptCreateHash failed");
        }

        if (!BCRYPT_SUCCESS(BCryptHashData(
                hashHandle,
                reinterpret_cast<PUCHAR>(const_cast<char*>(message.data())),
                static_cast<ULONG>(message.size()),
                0))) {
            throw std::runtime_error("BCryptHashData failed");
        }

        if (!BCRYPT_SUCCESS(BCryptFinishHash(hashHandle, hashBytes.data(), static_cast<ULONG>(hashBytes.size()), 0))) {
            throw std::runtime_error("BCryptFinishHash failed");
        }

        BCryptDestroyHash(hashHandle);
        BCryptCloseAlgorithmProvider(algorithmHandle, 0);
        return hashBytes;
    } catch (...) {
        if (hashHandle != NULL) {
            BCryptDestroyHash(hashHandle);
        }
        if (algorithmHandle != NULL) {
            BCryptCloseAlgorithmProvider(algorithmHandle, 0);
        }
        throw;
    }
}

std::string ComputeSignatureBase64(const ClientConfig& config, const ClientIdentity& identity, const std::string& timestamp, const std::string& nonce, const std::string& body) {
    const std::string material = timestamp + "\n" + nonce + "\n" + identity.clientId + "\n" + body;
    const std::vector<unsigned char> digest = ComputeHmacSha256(config.sharedSecret, material);
    return Base64Encode(digest);
}

std::wstring BuildApiPath(const ClientConfig& config, const std::wstring& suffix) {
    std::wstring base = config.apiBasePath;
    if (base.empty() || base.back() != L'/') {
        base += L"/";
    }

    if (!suffix.empty() && suffix.front() == L'/') {
        return base.substr(0, base.size() - 1) + suffix;
    }

    return base + suffix;
}

std::wstring BuildSignedHeaders(const ClientIdentity& identity, const std::string& timestamp, const std::string& nonce, const std::string& signature) {
    std::wostringstream stream;
    stream
        << L"Content-Type: application/json\r\n"
        << L"X-Monitor-Client-Id: " << Widen(identity.clientId) << L"\r\n"
        << L"X-Monitor-Timestamp: " << Widen(timestamp) << L"\r\n"
        << L"X-Monitor-Nonce: " << Widen(nonce) << L"\r\n"
        << L"X-Monitor-Signature: " << Widen(signature) << L"\r\n";
    return stream.str();
}

HttpResponse SendSignedJsonRequest(
    const ClientConfig& config,
    const ClientIdentity& identity,
    const std::wstring& method,
    const std::wstring& path,
    const std::string& body
) {
    WinHttpHandle session(WinHttpOpen(L"WorkActivityMonitor/2.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0));
    if (!session.IsValid()) {
        throw std::runtime_error("WinHttpOpen failed");
    }

    WinHttpSetTimeouts(session.Get(), 10000, 10000, 15000, 30000);

    WinHttpHandle connect(WinHttpConnect(session.Get(), config.serverHost.c_str(), static_cast<INTERNET_PORT>(config.serverPort), 0));
    if (!connect.IsValid()) {
        throw std::runtime_error("WinHttpConnect failed");
    }

    const DWORD requestFlags = config.useTls ? WINHTTP_FLAG_SECURE : 0;
    WinHttpHandle requestHandle(WinHttpOpenRequest(
        connect.Get(),
        method.c_str(),
        path.c_str(),
        NULL,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        requestFlags));
    if (!requestHandle.IsValid()) {
        throw std::runtime_error("WinHttpOpenRequest failed");
    }

    if (config.useTls && config.allowSelfSignedTls) {
        // Self-signed certificates are convenient for lab deployments, so the
        // behavior is configurable instead of hard-coded.
        DWORD securityFlags =
            SECURITY_FLAG_IGNORE_UNKNOWN_CA |
            SECURITY_FLAG_IGNORE_CERT_CN_INVALID |
            SECURITY_FLAG_IGNORE_CERT_DATE_INVALID |
            SECURITY_FLAG_IGNORE_CERT_WRONG_USAGE;
        WinHttpSetOption(requestHandle.Get(), WINHTTP_OPTION_SECURITY_FLAGS, &securityFlags, sizeof(securityFlags));
    }

    const std::string timestamp = GetUtcTimestamp();
    const std::string nonce = GenerateNonce();
    const std::string signature = ComputeSignatureBase64(config, identity, timestamp, nonce, body);
    const std::wstring headers = BuildSignedHeaders(identity, timestamp, nonce, signature);

    if (!WinHttpSendRequest(
            requestHandle.Get(),
            headers.c_str(),
            static_cast<DWORD>(headers.size()),
            const_cast<char*>(body.data()),
            static_cast<DWORD>(body.size()),
            static_cast<DWORD>(body.size()),
            0)) {
        throw std::runtime_error("WinHttpSendRequest failed");
    }

    if (!WinHttpReceiveResponse(requestHandle.Get(), NULL)) {
        throw std::runtime_error("WinHttpReceiveResponse failed");
    }

    DWORD statusCode = 0;
    DWORD size = sizeof(statusCode);
    if (!WinHttpQueryHeaders(requestHandle.Get(), WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX, &statusCode, &size, WINHTTP_NO_HEADER_INDEX)) {
        throw std::runtime_error("WinHttpQueryHeaders failed");
    }

    std::string responseBody;
    while (true) {
        DWORD bytesAvailable = 0;
        if (!WinHttpQueryDataAvailable(requestHandle.Get(), &bytesAvailable)) {
            throw std::runtime_error("WinHttpQueryDataAvailable failed");
        }

        if (bytesAvailable == 0) {
            break;
        }

        std::vector<char> buffer(bytesAvailable);
        DWORD bytesRead = 0;
        if (!WinHttpReadData(requestHandle.Get(), buffer.data(), bytesAvailable, &bytesRead)) {
            throw std::runtime_error("WinHttpReadData failed");
        }

        responseBody.append(buffer.data(), bytesRead);
    }

    return HttpResponse{statusCode, responseBody};
}

std::string ExtractJsonString(const std::string& json, const std::string& key) {
    const std::string pattern = "\"" + key + "\"";
    size_t position = json.find(pattern);
    if (position == std::string::npos) {
        return "";
    }

    position = json.find(':', position + pattern.size());
    if (position == std::string::npos) {
        return "";
    }

    ++position;
    while (position < json.size() && (json[position] == ' ' || json[position] == '\t' || json[position] == '\n' || json[position] == '\r')) {
        ++position;
    }

    if (position >= json.size() || json[position] != '"') {
        return "";
    }

    ++position;
    std::string result;
    while (position < json.size()) {
        const char symbol = json[position++];
        if (symbol == '\\' && position < json.size()) {
            result.push_back(json[position++]);
            continue;
        }
        if (symbol == '"') {
            return result;
        }
        result.push_back(symbol);
    }

    return "";
}

long long ExtractJsonInteger(const std::string& json, const std::string& key) {
    const std::string pattern = "\"" + key + "\"";
    size_t position = json.find(pattern);
    if (position == std::string::npos) {
        return 0;
    }

    position = json.find(':', position + pattern.size());
    if (position == std::string::npos) {
        return 0;
    }

    ++position;
    while (position < json.size() && (json[position] == ' ' || json[position] == '\t' || json[position] == '\n' || json[position] == '\r')) {
        ++position;
    }

    size_t end = position;
    while (end < json.size() && std::isdigit(static_cast<unsigned char>(json[end]))) {
        ++end;
    }

    if (end == position) {
        return 0;
    }

    try {
        return std::stoll(json.substr(position, end - position));
    } catch (...) {
        return 0;
    }
}

bool TryParseQueuedCommand(const std::string& json, QueuedCommand& command) {
    if (json.find("\"command\":null") != std::string::npos) {
        return false;
    }

    const long long id = ExtractJsonInteger(json, "id");
    const std::string commandType = ExtractJsonString(json, "command_type");
    if (id <= 0 || commandType.empty()) {
        return false;
    }

    command.id = id;
    command.commandType = commandType;
    return true;
}

std::string BuildHeartbeatJson(const ClientIdentity& identity, const ClientConfig& config, const std::string& appMode) {
    const unsigned long idleSeconds = GetIdleSeconds();
    const std::string activityState = GetActivityState(idleSeconds, static_cast<unsigned long>(config.idleThresholdSeconds));
    const auto lastActiveTime = std::chrono::system_clock::now() - std::chrono::seconds(idleSeconds);
    std::time_t lastActiveTimeT = std::chrono::system_clock::to_time_t(lastActiveTime);
    std::tm lastActiveTm = {};
    gmtime_s(&lastActiveTm, &lastActiveTimeT);

    char lastActiveBuffer[32] = {};
    std::strftime(lastActiveBuffer, sizeof(lastActiveBuffer), "%Y-%m-%dT%H:%M:%SZ", &lastActiveTm);

    std::ostringstream json;
    json
        << "{"
        << "\"client_id\":\"" << JsonEscape(identity.clientId) << "\","
        << "\"protocol_version\":" << kProtocolVersion << ","
        << "\"domain\":\"" << JsonEscape(identity.domain) << "\","
        << "\"machine\":\"" << JsonEscape(identity.machine) << "\","
        << "\"user\":\"" << JsonEscape(identity.user) << "\","
        << "\"ip_address\":\"" << JsonEscape(identity.ipAddress) << "\","
        << "\"activity_state\":\"" << JsonEscape(activityState) << "\","
        << "\"idle_seconds\":" << idleSeconds << ","
        << "\"last_active_at\":\"" << JsonEscape(lastActiveBuffer) << "\","
        << "\"app_mode\":\"" << JsonEscape(appMode) << "\","
        << "\"service_name\":\"" << JsonEscape(Narrow(config.serviceName)) << "\""
        << "}";
    return json.str();
}

std::string BuildCommandPollJson(const ClientIdentity& identity) {
    std::ostringstream json;
    json
        << "{"
        << "\"client_id\":\"" << JsonEscape(identity.clientId) << "\""
        << "}";
    return json.str();
}

std::string BuildCommandErrorJson(const ClientIdentity& identity, const std::string& error) {
    std::ostringstream json;
    json
        << "{"
        << "\"client_id\":\"" << JsonEscape(identity.clientId) << "\","
        << "\"error\":\"" << JsonEscape(error) << "\""
        << "}";
    return json.str();
}

std::string BuildScreenshotJson(const ClientIdentity& identity, const std::string& capturedAt, const std::string& base64Image) {
    std::ostringstream json;
    json
        << "{"
        << "\"client_id\":\"" << JsonEscape(identity.clientId) << "\","
        << "\"captured_at\":\"" << JsonEscape(capturedAt) << "\","
        << "\"image_base64\":\"" << JsonEscape(base64Image) << "\""
        << "}";
    return json.str();
}

bool ResponseIsSuccessful(const HttpResponse& response) {
    return response.statusCode >= 200 && response.statusCode < 300;
}

bool WaitForStopOrTimeout(HANDLE stopEvent, DWORD timeoutMilliseconds) {
    if (stopEvent == NULL) {
        Sleep(timeoutMilliseconds);
        return false;
    }
    return WaitForSingleObject(stopEvent, timeoutMilliseconds) == WAIT_OBJECT_0;
}

ClientIdentity BuildIdentityWithWinsock() {
    WinsockSession winsock;
    ClientIdentity identity;
    identity.domain = ReadEnvironmentVariable("USERDOMAIN");
    identity.machine = ReadComputerName();
    identity.user = ReadUserName();
    identity.ipAddress = winsock.IsInitialized() ? ResolveLocalIpAddress() : "";
    identity.clientId = MakeClientId(identity);
    return identity;
}

void SendHeartbeat(const ClientConfig& config, const ClientIdentity& identity, const std::string& appMode) {
    const std::string body = BuildHeartbeatJson(identity, config, appMode);
    const HttpResponse response = SendSignedJsonRequest(config, identity, L"POST", BuildApiPath(config, L"/client/heartbeat"), body);
    if (!ResponseIsSuccessful(response)) {
        throw std::runtime_error("Heartbeat request failed with HTTP status " + std::to_string(response.statusCode));
    }
}

bool PollNextCommand(const ClientConfig& config, const ClientIdentity& identity, QueuedCommand& command) {
    const std::string body = BuildCommandPollJson(identity);
    const HttpResponse response = SendSignedJsonRequest(config, identity, L"POST", BuildApiPath(config, L"/client/commands/poll"), body);
    if (!ResponseIsSuccessful(response)) {
        throw std::runtime_error("Command polling failed with HTTP status " + std::to_string(response.statusCode));
    }
    return TryParseQueuedCommand(response.body, command);
}

void ReportCommandFailure(const ClientConfig& config, const ClientIdentity& identity, long long commandId, const std::string& error) {
    const std::string body = BuildCommandErrorJson(identity, error);
    const std::wstring path = BuildApiPath(config, L"/client/commands/" + std::to_wstring(commandId) + L"/complete");
    const HttpResponse response = SendSignedJsonRequest(config, identity, L"POST", path, body);
    if (!ResponseIsSuccessful(response)) {
        throw std::runtime_error("Failed to report command error");
    }
}

void UploadScreenshotResult(const ClientConfig& config, const ClientIdentity& identity, long long commandId) {
    const std::vector<unsigned char> screenshotBytes = CaptureDesktopPng();
    const std::string imageBase64 = Base64Encode(screenshotBytes);
    const std::string body = BuildScreenshotJson(identity, GetUtcTimestamp(), imageBase64);
    const std::wstring path = BuildApiPath(config, L"/client/commands/" + std::to_wstring(commandId) + L"/screenshot");
    const HttpResponse response = SendSignedJsonRequest(config, identity, L"POST", path, body);
    if (!ResponseIsSuccessful(response)) {
        throw std::runtime_error("Screenshot upload failed with HTTP status " + std::to_string(response.statusCode));
    }
}

void ExecuteQueuedCommand(const ClientConfig& config, const ClientIdentity& identity, const QueuedCommand& command) {
    if (command.commandType == "capture_screenshot") {
        UploadScreenshotResult(config, identity, command.id);
        return;
    }

    ReportCommandFailure(config, identity, command.id, "Unsupported command type: " + command.commandType);
}

void UpdateServiceStatus(DWORD currentState, DWORD exitCode, DWORD waitHint) {
    if (g_serviceStatusHandle == NULL) {
        return;
    }

    g_serviceStatus.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    g_serviceStatus.dwCurrentState = currentState;
    g_serviceStatus.dwWin32ExitCode = exitCode;
    g_serviceStatus.dwWaitHint = waitHint;
    g_serviceStatus.dwControlsAccepted = currentState == SERVICE_START_PENDING ? 0 : SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN;
    SetServiceStatus(g_serviceStatusHandle, &g_serviceStatus);
}

void RunClientLoop(const ClientConfig& config, HANDLE stopEvent, const std::string& appMode) {
    const ClientIdentity identity = BuildIdentityWithWinsock();
    auto nextHeartbeat = std::chrono::steady_clock::now();
    auto nextCommandPoll = std::chrono::steady_clock::now();

    while (true) {
        const auto now = std::chrono::steady_clock::now();

        if (now >= nextHeartbeat) {
            try {
                SendHeartbeat(config, identity, appMode);
            } catch (...) {
                // Heartbeats are retried on the next interval, which keeps the agent
                // resilient to temporary HTTPS outages or certificate rotations.
            }
            nextHeartbeat = now + std::chrono::seconds(config.heartbeatIntervalSeconds);
        }

        if (now >= nextCommandPoll) {
            try {
                QueuedCommand command;
                if (PollNextCommand(config, identity, command)) {
                    try {
                        ExecuteQueuedCommand(config, identity, command);
                    } catch (const std::exception& error) {
                        try {
                            ReportCommandFailure(config, identity, command.id, error.what());
                        } catch (...) {
                        }
                    }
                }
            } catch (...) {
            }
            nextCommandPoll = now + std::chrono::seconds(config.commandPollIntervalSeconds);
        }

        if (WaitForStopOrTimeout(stopEvent, kLoopSleepMilliseconds)) {
            break;
        }
    }
}

bool InstallWindowsService(const ClientConfig& config) {
    const std::wstring binaryPath = L"\"" + GetExecutablePath() + L"\" --service";
    SC_HANDLE scmHandle = OpenSCManagerW(NULL, NULL, SC_MANAGER_CREATE_SERVICE);
    if (scmHandle == NULL) {
        return false;
    }

    SC_HANDLE serviceHandle = CreateServiceW(
        scmHandle,
        config.serviceName.c_str(),
        config.serviceDisplayName.c_str(),
        SERVICE_ALL_ACCESS,
        SERVICE_WIN32_OWN_PROCESS,
        SERVICE_AUTO_START,
        SERVICE_ERROR_NORMAL,
        binaryPath.c_str(),
        NULL,
        NULL,
        NULL,
        NULL,
        NULL);

    if (serviceHandle == NULL) {
        CloseServiceHandle(scmHandle);
        return false;
    }

    SERVICE_DESCRIPTIONW description = {};
    description.lpDescription = const_cast<LPWSTR>(config.serviceDescription.c_str());
    ChangeServiceConfig2W(serviceHandle, SERVICE_CONFIG_DESCRIPTION, &description);

    CloseServiceHandle(serviceHandle);
    CloseServiceHandle(scmHandle);
    return true;
}

bool UninstallWindowsService(const ClientConfig& config) {
    SC_HANDLE scmHandle = OpenSCManagerW(NULL, NULL, SC_MANAGER_CONNECT);
    if (scmHandle == NULL) {
        return false;
    }

    SC_HANDLE serviceHandle = OpenServiceW(scmHandle, config.serviceName.c_str(), SERVICE_STOP | DELETE | SERVICE_QUERY_STATUS);
    if (serviceHandle == NULL) {
        CloseServiceHandle(scmHandle);
        return false;
    }

    SERVICE_STATUS status = {};
    ControlService(serviceHandle, SERVICE_CONTROL_STOP, &status);
    const bool deleted = DeleteService(serviceHandle) == TRUE;

    CloseServiceHandle(serviceHandle);
    CloseServiceHandle(scmHandle);
    return deleted;
}

void WINAPI ServiceControlHandler(DWORD controlCode) {
    if (controlCode == SERVICE_CONTROL_STOP || controlCode == SERVICE_CONTROL_SHUTDOWN) {
        UpdateServiceStatus(SERVICE_STOP_PENDING, NO_ERROR, 5000);
        if (g_serviceStopEvent != NULL) {
            SetEvent(g_serviceStopEvent);
        }
    }
}

void WINAPI ServiceMain(DWORD, LPWSTR*) {
    g_serviceStatusHandle = RegisterServiceCtrlHandlerW(g_serviceConfig.serviceName.c_str(), ServiceControlHandler);
    if (g_serviceStatusHandle == NULL) {
        return;
    }

    UpdateServiceStatus(SERVICE_START_PENDING, NO_ERROR, 5000);
    g_serviceStopEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (g_serviceStopEvent == NULL) {
        UpdateServiceStatus(SERVICE_STOPPED, GetLastError(), 0);
        return;
    }

    UpdateServiceStatus(SERVICE_RUNNING, NO_ERROR, 0);
    RunClientLoop(g_serviceConfig, g_serviceStopEvent, "service");
    UpdateServiceStatus(SERVICE_STOPPED, NO_ERROR, 0);

    CloseHandle(g_serviceStopEvent);
    g_serviceStopEvent = NULL;
}

bool StartServiceDispatcher(const ClientConfig& config) {
    g_serviceConfig = config;

    SERVICE_TABLE_ENTRYW serviceTable[] = {
        {const_cast<LPWSTR>(g_serviceConfig.serviceName.c_str()), ServiceMain},
        {NULL, NULL},
    };
    return StartServiceCtrlDispatcherW(serviceTable) == TRUE;
}

}  // namespace

ClientConfig LoadConfig(const std::wstring& path) {
    ClientConfig config;
    std::ifstream file(path);
    if (!file.is_open()) {
        return config;
    }

    std::string line;
    std::string currentSection;
    while (std::getline(file, line)) {
        const size_t commentPosition = line.find_first_of("#;");
        if (commentPosition != std::string::npos) {
            line = line.substr(0, commentPosition);
        }

        line = Trim(line);
        if (line.empty()) {
            continue;
        }

        if (line.front() == '[' && line.back() == ']') {
            currentSection = ToLower(Trim(line.substr(1, line.size() - 2)));
            continue;
        }

        const size_t equalsPosition = line.find('=');
        if (equalsPosition == std::string::npos || currentSection != "client") {
            continue;
        }

        const std::string key = ToLower(Trim(line.substr(0, equalsPosition)));
        const std::string value = Trim(line.substr(equalsPosition + 1));

        if (key == "server_host") {
            config.serverHost = Widen(value);
        } else if (key == "server_port") {
            config.serverPort = std::max(1, ParseIntOrDefault(value, config.serverPort));
        } else if (key == "api_base_path") {
            config.apiBasePath = Widen(value);
        } else if (key == "heartbeat_interval_seconds") {
            config.heartbeatIntervalSeconds = std::max(5, ParseIntOrDefault(value, config.heartbeatIntervalSeconds));
        } else if (key == "command_poll_interval_seconds") {
            config.commandPollIntervalSeconds = std::max(2, ParseIntOrDefault(value, config.commandPollIntervalSeconds));
        } else if (key == "idle_threshold_seconds") {
            config.idleThresholdSeconds = std::max(5, ParseIntOrDefault(value, config.idleThresholdSeconds));
        } else if (key == "use_tls") {
            config.useTls = ParseBool(value);
        } else if (key == "allow_self_signed_tls") {
            config.allowSelfSignedTls = ParseBool(value);
        } else if (key == "enable_autostart") {
            config.enableAutostart = ParseBool(value);
        } else if (key == "registry_value_name") {
            config.registryValueName = Widen(value);
        } else if (key == "shared_secret") {
            config.sharedSecret = value;
        } else if (key == "service_name") {
            config.serviceName = Widen(value);
        } else if (key == "service_display_name") {
            config.serviceDisplayName = Widen(value);
        } else if (key == "service_description") {
            config.serviceDescription = Widen(value);
        }
    }

    return config;
}

void EnsureAutostartEnabled(const ClientConfig& config) {
    if (!config.enableAutostart) {
        return;
    }

    // Autostart is kept for the user-session mode, while service installation
    // is handled explicitly through the installer or command-line switch.
    const std::wstring executablePath = L"\"" + GetExecutablePath() + L"\"";
    WriteRegistryString(
        HKEY_CURRENT_USER,
        L"Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        config.registryValueName,
        executablePath
    );
}

ClientIdentity CollectClientIdentity() {
    return BuildIdentityWithWinsock();
}

std::string GetUtcTimestamp() {
    SYSTEMTIME systemTime;
    GetSystemTime(&systemTime);

    char buffer[32] = {};
    _snprintf_s(
        buffer,
        sizeof(buffer),
        _TRUNCATE,
        "%04d-%02d-%02dT%02d:%02d:%02dZ",
        systemTime.wYear,
        systemTime.wMonth,
        systemTime.wDay,
        systemTime.wHour,
        systemTime.wMinute,
        systemTime.wSecond
    );

    return buffer;
}

int WINAPI WinMain(HINSTANCE, HINSTANCE, LPSTR, int) {
    const std::wstring configPath = GetExecutableDirectory() + L"\\config.ini";
    const ClientConfig config = LoadConfig(configPath);

    int argc = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    std::vector<std::wstring> arguments;
    for (int index = 1; index < argc; ++index) {
        arguments.push_back(argv[index]);
    }
    if (argv != NULL) {
        LocalFree(argv);
    }

    for (const std::wstring& argument : arguments) {
        if (argument == L"--install-service") {
            return InstallWindowsService(config) ? 0 : 1;
        }
        if (argument == L"--uninstall-service") {
            return UninstallWindowsService(config) ? 0 : 1;
        }
        if (argument == L"--service") {
            return StartServiceDispatcher(config) ? 0 : 1;
        }
    }

    EnsureAutostartEnabled(config);
    RunClientLoop(config, NULL, "background");
    return 0;
}
