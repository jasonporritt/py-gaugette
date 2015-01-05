#----------------------------------------------------------------------
# ssd1351.py from https://github.com/guyc/py-gaugette
# ported by Jason Porritt,
# base on original work by Guy Carpenter for display.py
#
# This library works with 
#   Adafruit's 128x128 SPI color OLED   http://www.adafruit.com/products/1431
# 
# The code is based heavily on Adafruit's Arduino library
#   https://github.com/adafruit/Adafruit_SSD1351
# written by Limor Fried/Ladyada for Adafruit Industries.
#
# Some important things to know about this device and SPI:
#
# - The SPI interface has no MISO connection.  It is write-only.
#
# SPI and GPIO calls are made through an abstraction library that calls
# the appropriate library for the platform.
# For the RaspberryPi:
#     wiring2
#     spidev
# For the BeagleBone Black:
#     Adafruit_BBIO.SPI 
#     Adafruit_BBIO.GPIO
#
# - The pin connections between the BeagleBone Black SPI0 and OLED module are:
#
#      BBB    display
#      P9_17  -> CS
#      P9_15  -> RST   (arbirary GPIO, change at will)
#      P9_13  -> D/C   (arbirary GPIO, change at will)
#      P9_22  -> CLK
#      P9_18  -> DATA
#      P9_3   -> VIN
#      N/C    -> 3.3Vo
#      P9_1   -> GND
#----------------------------------------------------------------------

import gaugette.gpio
import gaugette.spi
import gaugette.font5x8
import time
import sys

class SSD1351:
    # SSD1351 Commands

    EXTERNAL_VCC   = 0x1
    SWITCH_CAP_VCC = 0x2

    MEMORY_MODE_HORIZ = 0x00
    MEMORY_MODE_VERT  = 0x01

    CMD_SETCOLUMN         = 0x15
    CMD_SETROW            = 0x75
    CMD_WRITERAM          = 0x5C
    CMD_READRAM           = 0x5D
    CMD_SETREMAP          = 0xA0
    CMD_STARTLINE         = 0xA1
    CMD_DISPLAYOFFSET     = 0xA2
    CMD_DISPLAYALLOFF     = 0xA4
    CMD_DISPLAYALLON      = 0xA5
    CMD_NORMALDISPLAY     = 0xA6
    CMD_INVERTDISPLAY     = 0xA7
    CMD_FUNCTIONSELECT    = 0xAB
    CMD_DISPLAYOFF        = 0xAE
    CMD_DISPLAYON         = 0xAF
    CMD_PRECHARGE         = 0xB1
    CMD_DISPLAYENHANCE    = 0xB2
    CMD_CLOCKDIV          = 0xB3
    CMD_SETVSL            = 0xB4
    CMD_SETGPIO           = 0xB5
    CMD_PRECHARGE2        = 0xB6
    CMD_SETGRAY           = 0xB8
    CMD_USELUT            = 0xB9
    CMD_PRECHARGELEVEL    = 0xBB
    CMD_VCOMH             = 0xBE
    CMD_CONTRASTABC       = 0xC1
    CMD_CONTRASTMASTER    = 0xC7
    CMD_MUXRATIO          = 0xCA
    CMD_COMMANDLOCK       = 0xFD
    CMD_HORIZSCROLL       = 0x96
    CMD_STOPSCROLL        = 0x9E
    CMD_STARTSCROLL       = 0x9F

    # Class constants are externally accessible as gaugette.display.display.CONST
    # or my_instance.CONST

    # Device name will be /dev/spidev-{bus}.{device}
    # dc_pin is the data/commmand pin.  This line is HIGH for data, LOW for command.
    # We will keep d/c low and bump it high only for commands with data
    # reset is normally HIGH, and pulled LOW to reset the display

    def __init__(self, bus=0, device=0, dc_pin="P9_15", reset_pin="P9_13", buffer_rows=256, buffer_cols=128, rows=128, cols=128):
        self.cols = cols
        self.rows = rows
        self.buffer_rows = buffer_rows
        self.mem_bytes = (self.buffer_rows * self.cols * 18) / 16 # total bytes in SSD1351 display ram
        self.dc_pin = dc_pin
        self.reset_pin = reset_pin
        self.spi = gaugette.spi.SPI(bus, device)
        self.gpio = gaugette.gpio.GPIO()
        self.gpio.setup(self.reset_pin, self.gpio.OUT)
        self.gpio.output(self.reset_pin, self.gpio.HIGH)
        self.gpio.setup(self.dc_pin, self.gpio.OUT)
        self.gpio.output(self.dc_pin, self.gpio.LOW)
        self.font = gaugette.font5x8.Font5x8
        self.col_offset = 0
        self.bitmap = self.Bitmap(buffer_cols, buffer_rows)
        self.flipped = False

    def reset(self):
        self.gpio.output(self.reset_pin, self.gpio.LOW)
        time.sleep(0.010) # 10ms
        self.gpio.output(self.reset_pin, self.gpio.HIGH)

    def command(self, *bytes):
        # already low
        # self.gpio.output(self.dc_pin, self.gpio.LOW) 
        self.spi.writebytes(list(bytes))

    def data(self, bytes):
        self.gpio.output(self.dc_pin, self.gpio.HIGH)
        #  chunk data to work around 255 byte limitation in adafruit implementation of writebytes
        # revisit - change to 1024 when Adafruit_BBIO is fixed.
        max_xfer = 255 if gaugette.platform == 'beaglebone' else 1024
        start = 0
        remaining = len(bytes)
        while remaining>0:
            count = remaining if remaining <= max_xfer else max_xfer
            remaining -= count
            self.spi.writebytes(bytes[start:start+count])
            start += count
        self.gpio.output(self.dc_pin, self.gpio.LOW)

    def begin(self, vcc_state = SWITCH_CAP_VCC):
        time.sleep(0.001) # 1ms
        self.reset()
        self.command(self.CMD_COMMANDLOCK, 0x12)
        self.command(self.CMD_COMMANDLOCK, 0xB1)
        self.command(self.CMD_DISPLAYOFF)
        self.command(self.CMD_CLOCKDIV, 0xF1)

        # support for 128x128 line mode
        if self.rows == 128:
            self.command(self.CMD_MUXRATIO, 127) 
            self.command(self.CMD_SETREMAP, 0x74)
        else:
          raise Exception('Unimplemented', 'Display sizes other than 128x128 are unsupported')

        self.command(self.CMD_SETCOLUMN, 0x00, 0x7F);
        self.command(self.CMD_SETROW, 0x00, 0x7F);

        # TODO Support 96-row display
        self.command(self.CMD_STARTLINE, 0x00);
        self.command(self.CMD_DISPLAYOFFSET, 0x00);
        self.command(self.CMD_SETGPIO, 0x00);
        self.command(self.CMD_FUNCTIONSELECT, 0x01);

        self.command(self.CMD_PRECHARGE, 0x32);
        self.command(self.CMD_VCOMH, 0x05);
        self.command(self.CMD_NORMALDISPLAY);
        self.command(self.CMD_CONTRASTABC, 0xC8, 0x80, 0xC8);
        self.command(self.CMD_CONTRASTMASTER, 0x0F);
        self.command(self.CMD_SETVSL, 0xA0, 0xB5, 0x55);

        self.command(self.CMD_PRECHARGE2, 0x01);
        self.command(self.CMD_DISPLAYON)


    def clear_display(self):
        self.bitmap.clear()

    def invert_display(self):
        self.command(self.CMD_INVERTDISPLAY)

    #def flip_display(self, flipped=True):
    #    self.flipped = flipped
    #    if flipped:
    #        self.command(self.COM_SCAN_INC)
    #        self.command(self.SEG_REMAP | 0x00)
    #    else:
    #        self.command(self.COM_SCAN_DEC)
    #        self.command(self.SET_COM_PINS, 0x02)

    def normal_display(self):
        self.command(self.CMD_NORMALDISPLAY)

    #def set_contrast(self, contrast=0x7f):
    #    self.command(self.SET_CONTRAST, contrast)

    def display(self):
        self.display_block(self.bitmap, 0, 0, self.cols, self.col_offset)

    def display_cols(self, start_col, count):
        self.display_block(self.bitmap, 0, start_col, count, self.col_offset)

    # Transfers data from the passed bitmap (instance of display.Bitmap)
    # starting at row <row> col <col>.
    # Both row and bitmap.rows will be divided by 8 to get page addresses,
    # so both must divide evenly by 8 to avoid surprises.
    #
    # bitmap:     instance of Bitmap
    #             The number of rows in the bitmap must be a multiple of 8.
    # row:        Starting row to write to - must be multiple of 8
    # col:        Starting col to write to.
    # col_count:  Number of cols to write.
    # col_offset: column offset in buffer to write from
    #  
    def display_block(self, bitmap, row, col, col_count, col_offset=0):
        page_count = bitmap.rows >> 3
        page_start = row >> 3
        page_end   = page_start + page_count - 1
        col_start  = col
        col_end    = col + col_count - 1
        self.command(self.CMD_SETREMAP, self.MEMORY_MODE_VERT)
        self.command(self.CMD_SETROW, page_start, page_end)
        self.command(self.CMD_SETCOLUMN, col_start, col_end)
        start = col_offset * page_count
        length = col_count * page_count
        self.data(bitmap.data[start:start+length])

    # Diagnostic print of the memory buffer to stdout 
    def dump_buffer(self):
        self.bitmap.dump()

    def draw_pixel(self, x, y, on=True):
        self.bitmap.draw_pixel(x,y,on)
        
    def draw_text(self, x, y, string):
        font_bytes = self.font.bytes
        font_rows = self.font.rows
        font_cols = self.font.cols
        for c in string:
            p = ord(c) * font_cols
            for col in range(0,font_cols):
                mask = font_bytes[p]
                p+=1
                for row in range(0,8):
                    self.draw_pixel(x,y+row,mask & 0x1)
                    mask >>= 1
                x += 1

    def draw_text2(self, x, y, string, size=2, space=1):
        font_bytes = self.font.bytes
        font_rows = self.font.rows
        font_cols = self.font.cols
        for c in string:
            p = ord(c) * font_cols
            for col in range(0,font_cols):
                mask = font_bytes[p]
                p+=1
                py = y
                for row in range(0,8):
                    for sy in range(0,size):
                        px = x
                        for sx in range(0,size):
                            self.draw_pixel(px,py,mask & 0x1)
                            px += 1
                        py += 1
                    mask >>= 1
                x += size
            x += space

    def clear_block(self, x0,y0,dx,dy):
        self.bitmap.clear_block(x0,y0,dx,dy)
        
    def draw_text3(self, x, y, string, font):
        return self.bitmap.draw_text(x,y,string,font)

    def text_width(self, string, font):
        return self.bitmap.text_width(string, font)

    class Bitmap:

        # TODO: Only functioning value is 16
        BITS_PER_PIXEL = 16
    
        # Pixels are stored in column-major order!
        # This makes it easy to reference a vertical slice of the display buffer
        # and we use the to achieve reasonable performance vertical scrolling 
        # without hardware support.
        def __init__(self, cols, rows):
            self.rows = rows
            self.cols = cols
            self.bytes_per_col = rows * (BITS_PER_PIXEL / 8) 
            self.data = [0] * (self.cols * self.bytes_per_col)

        def clear(self):
            for i in range(0,len(self.data)):
                self.data[i] = 0

        # Diagnostic print of the memory buffer to stdout 
        # TODO: Only works for BITS_PER_PIXEL value of 16
        def dump(self):
            for y in range(0, self.rows):
                mem_row = y * self.bytes_per_col
                line = ""
                for x in range(0, self.cols):
                    mem_col = x
                    offset = mem_row + self.rows * mem_col
                    if self.data[offset] > 0:
                        line += '*'
                    else:
                        line += ' '
                print('|'+line+'|')
                
        def draw_pixel(self, x, y, on=True):
            if (x<0 or x>=self.cols or y<0 or y>=self.rows):
                return
            mem_col = x
            mem_row = y / 8
            offset = mem_row + self.rows * mem_col
    
            if on:
                self.data[offset] = 0xF
            else:
                self.data[offset] = 0
    
        def clear_block(self, x0,y0,dx,dy):
            for x in range(x0,x0+dx):
                for y in range(y0,y0+dy):
                    self.draw_pixel(x,y,0)

        # returns the width in pixels of the string allowing for kerning & interchar-spaces
        def text_width(self, string, font):
            x = 0
            prev_char = None
            for c in string:
                if (c<font.start_char or c>font.end_char):
                    if prev_char != None:
                        x += font.space_width + prev_width + font.gap_width
                    prev_char = None
                else:
                    pos = ord(c) - ord(font.start_char)
                    (width,offset) = font.descriptors[pos]
                    if prev_char != None:
                        x += font.kerning[prev_char][pos] + font.gap_width
                    prev_char = pos
                    prev_width = width
                    
            if prev_char != None:
                x += prev_width
                
            return x
              
        def draw_text(self, x, y, string, font):
            height = font.char_height
            prev_char = None
    
            for c in string:
                if (c<font.start_char or c>font.end_char):
                    if prev_char != None:
                        x += font.space_width + prev_width + font.gap_width
                    prev_char = None
                else:
                    pos = ord(c) - ord(font.start_char)
                    (width,offset) = font.descriptors[pos]
                    if prev_char != None:
                        x += font.kerning[prev_char][pos] + font.gap_width
                    prev_char = pos
                    prev_width = width
                    
                    bytes_per_row = (width + 7) * (BITS_PER_PIXEL / 8)
                    for row in range(0,height):
                        py = y + row
                        mask = 0x80
                        p = offset
                        for col in range(0,width):
                            px = x + col
                            if (font.bitmaps[p] & mask):
                                self.draw_pixel(px,py,1)  # for kerning, never draw black
                            mask >>= 1
                            if mask == 0:
                                mask = 0x80
                                p+=1
                        offset += bytes_per_row
              
            if prev_char != None:
                x += prev_width
    
            return x

    ## This is a helper class to display a scrollable list of text lines.
    ## The list must have at least 1 item.
    #class ScrollingList:
    #    def __init__(self, display, list, font):
    #        self.display = display
    #        self.list = list
    #        self.font = font
    #        self.position = 0 # row index into list, 0 to len(list) * self.rows - 1
    #        self.offset = 0   # led hardware scroll offset
    #        self.pan_row = -1
    #        self.pan_offset = 0
    #        self.pan_direction = 1
    #        self.bitmaps = []
    #        self.rows = display.rows
    #        self.cols = display.cols
    #        self.bufrows = self.rows * 2
    #        downset = (self.rows - font.char_height)/2
    #        for text in list:
    #            width = display.cols
    #            text_bitmap = display.Bitmap(width, self.rows)
    #            width = text_bitmap.draw_text(0,downset,text,font)
    #            if width > 128:
    #                text_bitmap = display.Bitmap(width+15, self.rows)
    #                text_bitmap.draw_text(0,downset,text,font)
    #            self.bitmaps.append(text_bitmap)
    #            
    #        # display the first word in the first position
    #        self.display.display_block(self.bitmaps[0], 0, 0, self.cols)
    #
    #    # how many steps to the nearest home position
    #    def align_offset(self):
    #        pos = self.position % self.rows
    #        midway = (self.rows/2)
    #        delta = (pos + midway) % self.rows - midway
    #        return -delta

    #    def align(self, delay=0.005):
    #        delta = self.align_offset()
    #        if delta!=0:
    #            steps = abs(delta)
    #            sign = delta/steps
    #            for i in range(0,steps):
    #                if i>0 and delay>0:
    #                    time.sleep(delay)
    #                self.scroll(sign)
    #        return self.position / self.rows
    #
    #    # scroll up or down.  Does multiple one-pixel scrolls if delta is not >1 or <-1
    #    def scroll(self, delta):
    #        if delta == 0:
    #            return
    #
    #        count = len(self.list)
    #        step = cmp(delta, 0)
    #        for i in range(0,delta, step):
    #            if (self.position % self.rows) == 0:
    #                n = self.position / self.rows
    #                # at even boundary, need to update hidden row
    #                m = (n + step + count) % count
    #                row = (self.offset + self.rows) % self.bufrows
    #                self.display.display_block(self.bitmaps[m], row, 0, self.cols)
    #                if m == self.pan_row:
    #                    self.pan_offset = 0
    #            self.offset = (self.offset + self.bufrows + step) % self.bufrows
    #            self.display.command(self.display.SET_START_LINE | self.offset)
    #            max_position = count * self.rows
    #            self.position = (self.position + max_position + step) % max_position
    #
    #    # pans the current row back and forth repeatedly.
    #    # Note that this currently only works if we are at a home position.
    #    def auto_pan(self):
    #        n = self.position / self.rows
    #        if n != self.pan_row:
    #            self.pan_row = n
    #            self.pan_offset = 0
    #            
    #        text_bitmap = self.bitmaps[n]
    #        if text_bitmap.cols > self.cols:
    #            row = self.offset # this only works if we are at a home position
    #            if self.pan_direction > 0:
    #                if self.pan_offset <= (text_bitmap.cols - self.cols):
    #                    self.pan_offset += 1
    #                else:
    #                    self.pan_direction = -1
    #            else:
    #                if self.pan_offset > 0:
    #                    self.pan_offset -= 1
    #                else:
    #                    self.pan_direction = 1
    #            self.display.display_block(text_bitmap, row, 0, self.cols, self.pan_offset)
    #
