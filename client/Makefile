TARGET = Client.exe
CXX = x86_64-w64-mingw32-g++
CXXFLAGS = -std=c++17 -O2 -mwindows
LDFLAGS = -lws2_32 -lgdiplus -ladvapi32 -luser32 -lwinhttp -lbcrypt -lcrypt32 -lshell32 -lole32
SOURCES = Client.cpp activity_monitor.cpp screenshot.cpp

all: $(TARGET)

$(TARGET): $(SOURCES) client.h
	$(CXX) $(CXXFLAGS) -o $@ $(SOURCES) $(LDFLAGS)

clean:
	rm -f $(TARGET)
