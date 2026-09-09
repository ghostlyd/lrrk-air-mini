#pragma once
#include <pthread.h>
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(mux) pthread_mutex_lock(mux)
#define portEXIT_CRITICAL(mux) pthread_mutex_unlock(mux)
