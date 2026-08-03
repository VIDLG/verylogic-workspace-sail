#ifdef _WIN32

#include <stdarg.h>
#include <stdio.h>
#include <sys/types.h>
#include <time.h>

/* MinGW supplies POSIX-compatible types; the Windows SDK does not. */
#if !defined(__MINGW32__) && !defined(__MINGW64__)
#include <BaseTsd.h>
typedef SSIZE_T ssize_t;
typedef int clockid_t;
#endif

#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 0
#endif

int asprintf(char **buffer, const char *format, ...);
int clock_gettime(clockid_t clock_id, struct timespec *time);
ssize_t getline(char **line, size_t *capacity, FILE *stream);

#endif
