#----------------------------------------------------------------------
# Gaugette.GPIO from from https://github.com/guyc/py-gaugette
# Guy Carpenter, Clearwater Software
#
# This is an abstraction layer for SPI calls to isolate the 
# differences between the RasperryPi and BeagleBone Black implementations.
#
# On the RPi, we use spidev
# On the BBB, we use Adafruit_BBIO.SPI
#
#----------------------------------------------------------------------
import gaugette

class SPI:
    def __init__(self, bus, device):
           
        if (gaugette.platform == 'raspberrypi'):
            import spidev
            import spidev
            self.spi = spidev.SpiDev()
            self.spi.open(bus, device)
            self.writebytes = self.spi.writebytes
                
        elif (gaugette.platform == 'beaglebone'):
            import Adafruit_BBIO.SPI
            self.spi = Adafruit_BBIO.SPI.SPI(bus, device)
            self.writebytes = self.spi.writebytes

        else:
            raise NotImplementedError("Platform '%s' is not supported." % gaugette.platform)
