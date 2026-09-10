#pragma once
#include <sys/socket.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <unistd.h>
int fixture_socket(int, int, int);
int fixture_fcntl(int, int, ...);
int fixture_bind(int, const struct sockaddr *, socklen_t);
int fixture_getsockname(int, struct sockaddr *, socklen_t *);
ssize_t fixture_recvfrom(int, void *, size_t, int, struct sockaddr *, socklen_t *);
ssize_t fixture_sendto(int, const void *, size_t, int, const struct sockaddr *, socklen_t);
int fixture_close(int);
#define socket fixture_socket
#define fcntl fixture_fcntl
#define bind fixture_bind
#define getsockname fixture_getsockname
#define recvfrom fixture_recvfrom
#define sendto fixture_sendto
#define close fixture_close
