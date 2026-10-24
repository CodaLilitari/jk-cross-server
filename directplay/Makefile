CC = i686-w64-mingw32-gcc
CFLAGS = -std=c11 -O2 -Wall -Wextra -Werror -static-libgcc
LDLIBS = -ldplayx -lole32 -lws2_32 -luuid

all: gateway.exe wait_helper.exe

wait_helper.exe: wait_helper.c
	$(CC) $(CFLAGS) -o $@.tmp wait_helper.c -luser32
	mv -f $@.tmp $@

gateway.exe: gateway.c protocol.c protocol.h
	$(CC) $(CFLAGS) -o $@.tmp gateway.c protocol.c $(LDLIBS)
	mv -f $@.tmp $@

test: protocol.c protocol.h test_protocol.c
	cc -std=c11 -O2 -Wall -Wextra -Werror -o test_protocol.tmp protocol.c test_protocol.c
	./test_protocol.tmp
	rm -f test_protocol.tmp

clean:
	rm -f gateway.exe wait_helper.exe test_protocol.tmp

.PHONY: all clean test
