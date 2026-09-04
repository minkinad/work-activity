#ifndef WORK_ACTIVITY_CLIENT_H
#define WORK_ACTIVITY_CLIENT_H

#include <windows.h>
#include <winsock2.h>

#include <string>
#include <vector>

struct ClientConfig {
    std::wstring serverHost = L"127.0.0.1";
    int serverPort = 5000;
    std::wstring apiBasePath = L"/api/v1";
    int heartbeatIntervalSeconds = 15;
    int commandPollIntervalSeconds = 5;
    int idleThresholdSeconds = 300;
    bool useTls = true;
    bool allowSelfSignedTls = false;
    bool enableAutostart = false;
    std::wstring registryValueName = L"WorkActivityMonitor";
    std::wstring serviceName = L"WorkActivityMonitorSvc";
    std::wstring serviceDisplayName = L"Work Activity Monitor Service";
    std::wstring serviceDescription = L"Uploads activity telemetry and executes queued screenshot commands.";
    std::string sharedSecret;
};

struct ClientIdentity {
    std::string clientId;
    std::string domain;
    std::string machine;
    std::string user;
    std::string ipAddress;
};

ClientConfig LoadConfig(const std::wstring& path);
void EnsureAutostartEnabled(const ClientConfig& config);
ClientIdentity CollectClientIdentity();
unsigned long GetIdleSeconds();
std::string GetActivityState(unsigned long idleSeconds, unsigned long idleThresholdSeconds);
std::string GetUtcTimestamp();
std::vector<unsigned char> CaptureDesktopPng();

#endif
