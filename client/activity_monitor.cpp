#include "client.h"

unsigned long GetIdleSeconds() {
    // Windows keeps the tick count of the last user input, which is enough for
    // lightweight activity detection without a keyboard/mouse hook.
    LASTINPUTINFO inputInfo;
    inputInfo.cbSize = sizeof(LASTINPUTINFO);
    if (!GetLastInputInfo(&inputInfo)) {
        return 0;
    }

    const DWORD currentTick = GetTickCount();
    return static_cast<unsigned long>((currentTick - inputInfo.dwTime) / 1000);
}

std::string GetActivityState(unsigned long idleSeconds, unsigned long idleThresholdSeconds) {
    return idleSeconds >= idleThresholdSeconds ? "idle" : "active";
}
