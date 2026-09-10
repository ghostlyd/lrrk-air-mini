/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
static inline void lw_usb_uart_clear(uint8_t *buffer,size_t size)
{
    volatile uint8_t *p=buffer;
    while(size--) *p++=0;
}
