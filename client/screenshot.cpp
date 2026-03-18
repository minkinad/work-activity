#include "client.h"

#include <gdiplus.h>
#include <objidl.h>

#include <stdexcept>
#include <vector>

#pragma comment(lib, "gdiplus.lib")

namespace {

class GdiplusSession {
public:
    GdiplusSession() {
        Gdiplus::GdiplusStartupInput startupInput;
        if (Gdiplus::GdiplusStartup(&token_, &startupInput, NULL) != Gdiplus::Ok) {
            throw std::runtime_error("Failed to initialize GDI+");
        }
    }

    ~GdiplusSession() {
        Gdiplus::GdiplusShutdown(token_);
    }

private:
    ULONG_PTR token_ = 0;
};

int GetEncoderClsid(const WCHAR* mimeType, CLSID* clsid) {
    UINT encoderCount = 0;
    UINT bufferSize = 0;
    Gdiplus::GetImageEncodersSize(&encoderCount, &bufferSize);
    if (bufferSize == 0) {
        return -1;
    }

    std::vector<unsigned char> buffer(bufferSize);
    auto* encoders = reinterpret_cast<Gdiplus::ImageCodecInfo*>(buffer.data());
    Gdiplus::GetImageEncoders(encoderCount, bufferSize, encoders);

    for (UINT index = 0; index < encoderCount; ++index) {
        if (wcscmp(encoders[index].MimeType, mimeType) == 0) {
            *clsid = encoders[index].Clsid;
            return static_cast<int>(index);
        }
    }

    return -1;
}

std::vector<unsigned char> SaveBitmapToPngBytes(HBITMAP bitmapHandle) {
    CLSID pngClsid;
    if (GetEncoderClsid(L"image/png", &pngClsid) < 0) {
        throw std::runtime_error("PNG encoder not found");
    }

    IStream* stream = NULL;
    if (CreateStreamOnHGlobal(NULL, TRUE, &stream) != S_OK) {
        throw std::runtime_error("Failed to create memory stream");
    }

    std::vector<unsigned char> bytes;
    try {
        Gdiplus::Bitmap bitmap(bitmapHandle, NULL);
        if (bitmap.Save(stream, &pngClsid, NULL) != Gdiplus::Ok) {
            throw std::runtime_error("Failed to save bitmap to PNG");
        }

        HGLOBAL globalHandle = NULL;
        if (GetHGlobalFromStream(stream, &globalHandle) != S_OK) {
            throw std::runtime_error("Failed to read image stream");
        }

        const SIZE_T size = GlobalSize(globalHandle);
        const void* data = GlobalLock(globalHandle);
        if (data == NULL || size == 0) {
            throw std::runtime_error("Failed to access PNG data");
        }

        const auto* byteData = static_cast<const unsigned char*>(data);
        bytes.assign(byteData, byteData + size);
        GlobalUnlock(globalHandle);
        stream->Release();
        return bytes;
    } catch (...) {
        stream->Release();
        throw;
    }
}

}  // namespace

std::vector<unsigned char> CaptureDesktopPng() {
    // The client sends screenshots as PNG bytes over HTTPS, so the capture code
    // renders directly into an in-memory stream instead of writing a temp file.
    GdiplusSession gdiplus;

    HWND desktop = GetDesktopWindow();
    HDC screenDc = GetDC(desktop);
    HDC memoryDc = CreateCompatibleDC(screenDc);
    if (screenDc == NULL || memoryDc == NULL) {
        if (memoryDc != NULL) {
            DeleteDC(memoryDc);
        }
        if (screenDc != NULL) {
            ReleaseDC(desktop, screenDc);
        }
        throw std::runtime_error("Failed to create device contexts");
    }

    const int width = GetSystemMetrics(SM_CXSCREEN);
    const int height = GetSystemMetrics(SM_CYSCREEN);
    HBITMAP bitmapHandle = CreateCompatibleBitmap(screenDc, width, height);
    if (bitmapHandle == NULL) {
        DeleteDC(memoryDc);
        ReleaseDC(desktop, screenDc);
        throw std::runtime_error("Failed to create bitmap");
    }

    HGDIOBJ previousObject = SelectObject(memoryDc, bitmapHandle);
    if (!BitBlt(memoryDc, 0, 0, width, height, screenDc, 0, 0, SRCCOPY | CAPTUREBLT)) {
        SelectObject(memoryDc, previousObject);
        DeleteObject(bitmapHandle);
        DeleteDC(memoryDc);
        ReleaseDC(desktop, screenDc);
        throw std::runtime_error("Failed to capture desktop");
    }

    SelectObject(memoryDc, previousObject);

    try {
        std::vector<unsigned char> result = SaveBitmapToPngBytes(bitmapHandle);
        DeleteObject(bitmapHandle);
        DeleteDC(memoryDc);
        ReleaseDC(desktop, screenDc);
        return result;
    } catch (...) {
        DeleteObject(bitmapHandle);
        DeleteDC(memoryDc);
        ReleaseDC(desktop, screenDc);
        throw;
    }
}
