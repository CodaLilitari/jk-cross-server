/* SPDX-License-Identifier: MIT
 * Wait for the original DP5 helper's message window without consuming its
 * startup/ack events. The class name comes from the original helper binary.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
    DWORD start=GetTickCount();
    if(argc==2 && !strcmp(argv[1],"--stop")) {
        HWND window=FindWindowA("DPlayHelpWndClass",NULL);
        DWORD thread;
        if(!window)return 0;
        thread=GetWindowThreadProcessId(window,NULL);
        if(!thread || !PostThreadMessageA(thread,WM_QUIT,0,0))return 1;
        puts("Original DirectPlay helper asked to exit its message loop");
        return 0;
    }
    if(argc!=1)return 2;
    while(GetTickCount()-start<20000u) {
        if(FindWindowA("DPlayHelpWndClass",NULL)) {
            puts("Original DirectPlay helper window is ready");
            return 0;
        }
        Sleep(100);
    }
    fputs("Original DirectPlay helper window did not become ready\n",stderr);
    return 1;
}
