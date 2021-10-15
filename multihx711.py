################################################################################################
# Todo 
# 1. Channel B
# 2. Consistentcy Check
# 3. Debug Mode Printing
# 4.

################################################################################################

import RPi.GPIO as GPIO
import threading
import time
import numpy as np


class MultiHX711():
    def __init__(self, num_mod=3, pin_DT=(5, 16, 17), pin_SCK=6, chA_gain=128, existing_chB=False, 
                 input_vol=5, output_vol_correction=True, debug_mode=False):

        # check consistency
        # Todo : Update
        if len(pin_DT) != num_mod:
            raise ValueError("Module's number (num_mod) is not consistent with length of pin_DT ")
        elif not isinstance(num_mod, int):
            raise ValueError("Module's number (num_mod) should be integer")
        elif not isinstance(pin_DT, (int, tuple)):
            raise ValueError("Module's number (num_mod) should be integer")

        # define variables
        self.num_mod = num_mod
        self.pin_DT = pin_DT
        self.pin_SCK = pin_SCK
        self.existing_chB = existing_chB
        self.chA_gain = chA_gain
        self.input_vol = input_vol
        self.output_vol_correction = output_vol_correction
        self.prev_raw_value = [0.,] * self.num_mod
        self.prev_vol_value = [0.,] * self.num_mod
        self.binary_max_value = "111111111111111111111111"
        self.debug_mode = debug_mode
        self.is_ch_updated = [True] * self.num_mod

        # conduct initialization of module
        self._GPIO_initialize()


    def _GPIO_initialize(self):

        # set specification method of pins
        GPIO.setmode(GPIO.BCM)

        # setup voltage reading channel (input to raspberry pi)
        for i in range(self.num_mod):
            GPIO.setup(self.pin_DT[i], GPIO.IN)
        
        # setup serial clock  channel (output from raspberry pi)
        # Todo : Support multi serial clock
        GPIO.setup(self.pin_SCK, GPIO.OUT)

        # something to be needed
        self.readLock = threading.Lock()
        self.power_down()
        self.power_up()


    def power_down(self):
        
        self.readLock.acquire()
        GPIO.output(self.pin_SCK, False)
        GPIO.output(self.pin_SCK, True)
        time.sleep(0.0001)
        self.readLock.release()
    

    def power_up(self):
        
        self.readLock.acquire()
        GPIO.output(self.pin_SCK, False)
        time.sleep(0.0001)
        self.readLock.release()

        self.read_value()
    
    
    def read_value(self):
        
        # confirm updating
        for i in range(self.num_mod):
            if not self.is_ch_updated[i]:
                self.is_ch_updated[i] = (GPIO.input(self.pin_DT[i]) == 0)

        # read value
        is_updated = True
        for i in range(self.num_mod):
            is_updated *= self.is_ch_updated[i]
        
        if is_updated:
            self.readLock.acquire()
            
            temp_binary_value = [""] * self.num_mod
            
            for i in range(24):
                GPIO.output(self.pin_SCK, True)
                GPIO.output(self.pin_SCK, False)
                
                for j in range(self.num_mod):
                    temp_binary_value[j] += str(GPIO.input(self.pin_DT[j]))

            if self.debug_mode:
                print(temp_binary_value)
            
            for i in range(self.num_mod):
                self.prev_raw_value[i] = int(temp_binary_value[i][1:], 2) - int(int(temp_binary_value[i][0]) << (len(temp_binary_value[i]) - 1))
                self.prev_vol_value[i] = self.prev_raw_value[i] / int(self.binary_max_value, 2) * (self.input_vol / self.chA_gain) * 1000

            if self.chA_gain == 128:
                num_pulse = 1
            elif self.chA_gain == 64:
                num_pulse = 3
            else:
                num_pulse = 1

            for i in range(num_pulse):
                GPIO.output(self.pin_SCK, True)
                GPIO.output(self.pin_SCK, False)
            
            for i in range(self.num_mod):
                self.is_ch_updated[i] = False
            
            self.readLock.release()

        if self.output_vol_correction:
            return (is_updated, self.prev_vol_value)
        else:
            return (is_updated, self.prev_raw_value)
    

    def cleanup(self):
        GPIO.cleanup()

def main():
   hx = MultiHX711(num_mod=1, pin_DT=(5,), debug_mode=False)
   while True:
       foo, bar = hx.read_value()
       if foo:
           print(foo, bar)

if __name__ == "__main__":
    main()
