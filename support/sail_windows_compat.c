#ifdef _WIN32

#include "sail_windows_compat.h"

#include <stdlib.h>
#include <sys/timeb.h>

int clock_gettime(clockid_t clock_id, struct timespec *time) {
  (void)clock_id;
  struct _timeb now;
  _ftime(&now);
  time->tv_sec = now.time;
  time->tv_nsec = now.millitm * 1000000L;
  return 0;
}

int asprintf(char **buffer, const char *format, ...) {
  va_list arguments;
  va_start(arguments, format);
  int length = _vscprintf(format, arguments);
  va_end(arguments);
  if (length < 0) return -1;

  *buffer = malloc((size_t)length + 1);
  if (*buffer == NULL) return -1;

  va_start(arguments, format);
  int written = vsnprintf(*buffer, (size_t)length + 1, format, arguments);
  va_end(arguments);
  return written;
}

/* Sail's C runtime uses POSIX getline(), which MinGW does not provide. */
ssize_t getline(char **line, size_t *capacity, FILE *stream) {
  if (line == NULL || capacity == NULL || stream == NULL) return -1;

  if (*line == NULL || *capacity == 0) {
    *capacity = 128;
    *line = malloc(*capacity);
    if (*line == NULL) return -1;
  }

  size_t length = 0;
  int character;
  while ((character = fgetc(stream)) != EOF) {
    if (length + 1 >= *capacity) {
      size_t next_capacity = *capacity * 2;
      char *next_line = realloc(*line, next_capacity);
      if (next_line == NULL) return -1;
      *line = next_line;
      *capacity = next_capacity;
    }

    (*line)[length++] = (char)character;
    if (character == '\n') break;
  }

  if (length == 0 && character == EOF) return -1;
  (*line)[length] = '\0';
  return (ssize_t)length;
}

#endif
