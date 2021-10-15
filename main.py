from multihx711 import MultiHX711
import adafruit_ads1x15.ads1115 as ADS
import adafruit_mcp4725 as MCP
from adafruit_ads1x15.analog_in import AnalogIn
import asyncio
import board
import busio
from collections import deque
import copy
import csv
import numpy as np
import math
import multiprocessing as mp
import PySimpleGUI as sg
import sys
import time


class Window():
    def __init__(self):
        # variables for adc
        self.max_num_queue_read = 100
        self.num_module = 4

        # variables for dac and loading control
        self.vol_out_interval = 0.5
        self.control_param = np.zeros((8, 4))
        self.is_controling = False
        self.adc_amp_factor = 100                 # N/Voltage
        self.current_control_option = 0
        self.start_time_cur_step = time.time()
        self.current_output_vol = 0
        self.base_elastic_modulus = 10000
        
        # variables for updating window
        self.update_window_interval = 1.

        # variables for calibration
        self.slope = [1., 1., 1., 1.]
        self.intercept = [0., 0., 0., 0.]
        
        # specimen parameters
        specimen_height = 150.
        specimen_diameter = 150.
        drain_tank_diameter = 84.
        rho_s = 2.69
        self.specimen_parameter = [specimen_height,
                                   specimen_diameter, 
                                   specimen_diameter ** 2 / 4 * math.pi,
                                   specimen_diameter ** 2 / 4 * math.pi * specimen_height,
                                   drain_tank_diameter,
                                   drain_tank_diameter ** 2 / 4 * math.pi,
                                   rho_s]

        # varialbles related to saving and monitoring
        self.save_interval = 1
        self.save_dir = "(file path)"
        self.is_saving_allowed = False
        self.is_avialable_window = mp.Value("i", 1)
        self.is_ch_updated = np.array([True] * self.num_module)

        self.read_value = [mp.Queue(maxsize=self.max_num_queue_read) for i in range(self.num_module)]
        self.current_vol = [0.] * self.num_module
        self.current_phi_val = [0.] * self.num_module
        self.current_output_param = [0.] * 5
        
        self._initialize_ADC_DAC()
        self._intiialize_window()
        self._update_window()

    def _initialize_ADC_DAC(self):
        print("initializing start (ADC/DAC)")
        self.hx = MultiHX711()
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.ads = ADS.ADS1115(self.i2c, address=0x48)
        self.dac = MCP.MCP4725(self.i2c, address=0x60)
        print("initializing end   (ADC/DAC)")
        
    
    def _intiialize_window(self):
        print("initializing start (window)")
        layout_calibration = sg.Frame("Calibration", [[sg.Text("CH No.", size=(13, 1), justification="center"), 
                                                       sg.Text("Param A (Slope)", size=(16, 1), justification="center"), 
                                                       sg.Text("Param B (Intercept)", size=(16, 1), justification="center"),
                                                       sg.Text("Tare", size=(4, 1), justification="center")],
                                                      [sg.Text("CH0 (LC_odo)", size=(13, 1)), 
                                                       sg.InputText(self.slope[0], enable_events=True, key='slope_change_CH0', size=(16, 1)), 
                                                       sg.InputText(self.intercept[0], key='intercept_change_CH0', enable_events=True, size=(16, 1)),
                                                       sg.Button("CH0", key='tare_CH0', disabled=False, size=(4, 1))],
                                                      [sg.Text("CH1 (DG_odo)", size=(13, 1)), 
                                                       sg.InputText(self.slope[1], enable_events=True, key='slope_change_CH1', size=(16, 1)), 
                                                       sg.InputText(self.intercept[1], key='intercept_change_CH1', enable_events=True, size=(16, 1)),
                                                       sg.Button("CH1", key='tare_CH1', disabled=False, size=(4, 1))],
                                                      [sg.Text("CH2 (LC_tank)", size=(13, 1)), 
                                                       sg.InputText(self.slope[2], enable_events=True, key='slope_change_CH2', size=(16, 1)), 
                                                       sg.InputText(self.intercept[2], key='intercept_change_CH2', enable_events=True, size=(16, 1)),
                                                       sg.Button("CH2", key='tare_CH2', disabled=False, size=(4, 1))],
                                                      [sg.Text("CH3 (PG_tank)", size=(13, 1)), 
                                                       sg.InputText(self.slope[3], enable_events=True, key='slope_change_CH3', size=(16, 1)), 
                                                       sg.InputText(self.intercept[3], key='intercept_change_CH3', enable_events=True, size=(16, 1)),
                                                       sg.Button("CH3", key='tare_CH3', disabled=False, size=(4, 1))]],
                                      vertical_alignment="top")
        layout_specimen_value = sg.Frame("Specimen Data", [[sg.Text("Specimen Height (mm)", size=(24, 1)),
                                                            sg.InputText(self.specimen_parameter[0], enable_events=True, key='specimen_parameter_0', size=(10, 1))],
                                                           [sg.Text("Specimen Diameter (mm)", size=(24, 1)),
                                                            sg.InputText(self.specimen_parameter[1], enable_events=True, key='specimen_parameter_1', size=(10, 1))],
                                                           [sg.Text("Specimen Area (mm2)", size=(24, 1)),
                                                            sg.InputText(self.specimen_parameter[2], readonly=True, enable_events=True, key='specimen_parameter_2', size=(10, 1))],
                                                           [sg.Text("Specimen Volume (mm3)", size=(24, 1)),
                                                            sg.InputText(self.specimen_parameter[3], readonly=True, enable_events=True, key='specimen_parameter_3', size=(10, 1))],
                                                           [sg.Text("Drain Tank Diameter (mm)", size=(24, 1)),
                                                            sg.InputText(self.specimen_parameter[4], enable_events=True, key='specimen_parameter_4', size=(10, 1))],
                                                           [sg.Text("Drain Tank Area (mm2)", size=(24, 1)),
                                                            sg.InputText(self.specimen_parameter[5], readonly=True, enable_events=True, key='specimen_parameter_5', size=(10, 1))],
                                                           [sg.Text("ρ_s (g/cm3)", size=(24, 1)),
                                                            sg.InputText(self.specimen_parameter[6], enable_events=True, key='specimen_parameter_6', size=(10, 1))]],
                                         vertical_alignment="top")
        layout_output_value = sg.Frame("Output Value", [[sg.Text("CH No.", size=(13, 1), justification="center"), 
                                                         sg.Text("Raw Voltage(mV)", size=(16, 1), justification="center"), 
                                                         sg.Text("Phisical Value", size=(16, 1), justification="center")],
                                                        [sg.Text("CH0 (LC_odo)", size=(13, 1)), 
                                                         sg.InputText(self.current_vol[0], readonly=True, key='vol_CH0', size=(16, 1)), 
                                                         sg.InputText(self.current_phi_val[0], key='phi_val_CH0', readonly=True, enable_events=True, size=(16, 1)),
                                                         sg.Text("(N)", size=(7, 1))],
                                                        [sg.Text("CH1 (DG_odo)", size=(13, 1)), 
                                                         sg.InputText(self.current_vol[1], readonly=True, key='vol_CH1', size=(16, 1)), 
                                                         sg.InputText(self.current_phi_val[1], key='phi_val_CH1', readonly=True, enable_events=True, size=(16, 1)),
                                                         sg.Text("(mm)", size=(7, 1))],
                                                        [sg.Text("CH2 (LC_tank)", size=(13, 1)), 
                                                         sg.InputText(self.current_vol[2], readonly=True, key='vol_CH2', size=(16, 1)), 
                                                         sg.InputText(self.current_phi_val[2], key='phi_val_CH2', readonly=True, enable_events=True, size=(16, 1)),
                                                         sg.Text("(N)", size=(7, 1))],
                                                        [sg.Text("CH3 (PG_tank)", size=(13, 1)), 
                                                         sg.InputText(self.current_vol[3], readonly=True, key='vol_CH3', size=(16, 1)), 
                                                         sg.InputText(self.current_phi_val[3], key='phi_val_CH3', readonly=True, enable_events=True, size=(16, 1)),
                                                         sg.Text("(kPa)", size=(7, 1))]],
                                       vertical_alignment="top")
        layout_output_param = sg.Frame("Output Param", [[sg.Text("σ_a", size=(19, 1)),
                                                         sg.InputText(self.current_output_param[0], readonly=True, enable_events=True, key='current_output_param_0', size=(10, 1)),
                                                         sg.Text("(kPa)", size=(5, 1))],
                                                        [sg.Text("ɛ_a", size=(19, 1)),
                                                         sg.InputText(self.current_output_param[1], readonly=True, enable_events=True, key='current_output_param_1', size=(10, 1)),
                                                         sg.Text("(%)", size=(5, 1))],
                                                        [sg.Text("Discharged Volume", size=(19, 1)),
                                                         sg.InputText(self.current_output_param[2], readonly=True, enable_events=True, key='current_output_param_2', size=(10, 1)),
                                                         sg.Text("(mm3)", size=(5, 1))],
                                                        [sg.Text("Discharged Water", size=(19, 1)),
                                                         sg.InputText(self.current_output_param[3], readonly=True, enable_events=True, key='current_output_param_3', size=(10, 1)),
                                                         sg.Text("(mm3)", size=(5, 1))],
                                                        [sg.Text("Volume %", size=(19, 1)),
                                                         sg.InputText(self.current_output_param[4], readonly=True, enable_events=True, key='current_output_param_4', size=(10, 1)),
                                                         sg.Text("(%)", size=(5, 1))],
                                                        [sg.Text("Output V", size=(19, 1)),
                                                         sg.InputText(self.current_output_vol, readonly=False, enable_events=True, key='current_output_param_5', size=(10, 1)),
                                                         sg.Text("(V)", size=(5, 1))]],
                                       vertical_alignment="top")
        layout_record = sg.Frame("Record and Output", [[sg.InputText(default_text="(file path)", enable_events=True, key="save_file_path", size=(25, 1), readonly=True)],
                                            [sg.Text("Sampling Rate", size=(12, 1)),
                                             sg.InputText(self.save_interval, key='save_interval', size=(5, 1)),
                                             sg.Text("(Hz)", size=(4, 1))],
                                            [sg.Text("Window Rate", size=(12, 1)),
                                             sg.InputText(self.update_window_interval, readonly=True, key='window_interval', size=(5, 1)),
                                             sg.Text("(Hz)", size=(4, 1))],
                                            [sg.Text("ADC Output Rate", size=(12, 1)),
                                             sg.InputText(self.vol_out_interval, readonly=True, key='adc_output_interval', size=(5, 1)),
                                             sg.Text("(Hz)", size=(4, 1))],
                                            [sg.FileSaveAs(button_text="Start Saving", key='start_saving', target="save_file_path", default_extension=".csv", size=(8, 1)), 
                                             sg.Button("Stop Saving", disabled=True, key='stop_saving', size=(8, 1))],
                                            [sg.Button("Start Control", key='start_control', size=(8, 1)), 
                                             sg.Button("Stop Control", disabled=True, key='stop_control', size=(8, 1))]],
                                 vertical_alignment="top")
        layout_control = sg.Frame("Control Option", [[sg.Radio("No Control", size=(10, 1), default=True, group_id=0, key="control_option_0", enable_events=True), 
                                                      sg.Radio("Creep", size=(16, 1), group_id=0, key="control_option_1", enable_events=True), 
                                                      sg.Radio("Monotonic Loading", size=(16, 1), group_id=0, key="control_option_2", enable_events=True), 
                                                      sg.Radio("Cyclic Loading", size=(16, 1), group_id=0, key="control_option_3", enable_events=True)],
                                                     [sg.Text("", size=(15, 1)),
                                                      sg.Text("σ/ɛ", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_0_1", enable_events=True),
                                                      sg.Text("Com/Ext", size=(11, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_0_2", enable_events=True),
                                                      sg.Text("σ/ɛ", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_0_3", enable_events=True)],
                                                     [sg.Text("", size=(15, 1)),
                                                      sg.Text("Time", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_1_1", enable_events=True),
                                                      sg.Text("Target σ", size=(11, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_1_2", enable_events=True),
                                                      sg.Text("Com/Ext", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_1_3", enable_events=True)],
                                                     [sg.Text("", size=(15, 1)),
                                                      sg.Text("Target σ/ɛ", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_2_1", enable_events=True),
                                                      sg.Text("Target ɛ", size=(11, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_2_2", enable_events=True),
                                                      sg.Text("Max σ/ɛ", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_2_3", enable_events=True)],
                                                     [sg.Text("", size=(15, 1)),
                                                      sg.Text("Tol. σ/ɛ", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_3_1", enable_events=True),
                                                      sg.Text("Stress Rate", size=(11, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_3_2", enable_events=True),
                                                      sg.Text("Min σ/ɛ", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_3_3", enable_events=True)],
                                                     [sg.Text("", size=(15, 1)),
                                                      sg.Text("Limited σ/ɛ", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_4_1", enable_events=True),
                                                      sg.Text("Tol. σ", size=(11, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_4_2", enable_events=True),
                                                      sg.Text("Stress Rate", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_4_3", enable_events=True)],
                                                     [sg.Text("", size=(15, 1)),
                                                      sg.Text("Stress Rate", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_5_1", enable_events=True),
                                                      sg.Text("Tol. ɛ", size=(11, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_5_2", enable_events=True),
                                                      sg.Text("Nc", size=(12, 1)),
                                                      sg.InputText(0, size=(6, 1), key="control_param_5_3", enable_events=True)]],
                                  vertical_alignment="top")
        
        layout_all =[[layout_calibration, layout_specimen_value], [layout_output_value, layout_output_param], [layout_record, layout_control]]
        
        # create window
        self.window = sg.Window('DigitShowBasic Mini', layout_all, finalize=True)
        print("initializing end (window)")
    
    def _update_window(self):
        # ------- initialize hx711 module --------
        process_adc = mp.Process(target=self._read_adc)
        process_adc.start()
        
        temp_save_triggered_time = time.time()
        temp_update_variable_triggered_time = time.time()
        temp_control_triggered_time = time.time()
        
        
        while True:
            
            event, values = self.window.read(timeout=0.001)
            
            if event == sg.WIN_CLOSED or event == 'Cancel':
                self.is_windowing.value = False
                break

            if event != "__TIMEOUT__":
                self._import_event(event, values)
            
            is_update_ellapsed_time = (time.time() - temp_update_variable_triggered_time) > self.update_window_interval
            
            if is_update_ellapsed_time:
                self._update_variable()
                temp_update_variable_triggered_time = time.time() 
            
            is_saving_ellapsed_time = (time.time() - temp_save_triggered_time) > self.save_interval
            is_all_ch_updated = np.prod(self.is_ch_updated)
            
            if self.is_saving_allowed and is_saving_ellapsed_time and is_all_ch_updated:
                self._save_data()
                self.is_ch_updated = np.array([False] * self.num_module)
                temp_save_triggered_time = time.time()
            
            is_controling_ellapsed_time = (time.time() - temp_control_triggered_time) > self.vol_out_interval
            if self.is_controling and is_controling_ellapsed_time:
                self._control_adc_output()
                temp_control_triggered_time = time.time()
        
        process_hx711.join()
        
        GPIO.cleanup()
        self.window.close()
        sys.exit()
        
        
    def _read_adc(self):
        
        while self.is_avialable_window:
            is_updated, hx711_read_value = self.hx.read_value()
            if is_updated:
                for i in range(3):
                    temp_2 = hx711_read_value[i]
                    self.read_value[i].put(temp_2)
            
            temp_1 = AnalogIn(self.ads, ADS.P0).voltage
            self.read_value[3].put(temp_1)
    
    def _update_variable(self):
        for i in range(self.num_module):
            queue_size = self.read_value[i].qsize()
            
            if queue_size != 0:
                current_queue_value = np.array([])
                for j in range(queue_size):
                    temp_3 = self.read_value[i].get()
                    current_queue_value = np.append(current_queue_value, temp_3)
                
                self.current_vol[i] = np.median(current_queue_value)
                self.current_phi_val[i] = self.slope[i] * self.current_vol[i] + self.intercept[i]
                
                vol_element_key = "vol_CH" + str(i)
                phi_val_element_key =  "phi_val_CH" + str(i)
                
                self.window.Element(vol_element_key).Update(value="{:.6f}".format(self.current_vol[i]))
                self.window.Element(phi_val_element_key).Update(value="{:.6f}".format(self.current_phi_val[i]))
                
                self.is_ch_updated[i] = True
        
        
        self.current_output_param[0] = self.current_phi_val[0] / self.specimen_parameter[2] * 1000
        self.current_output_param[1] = (self.specimen_parameter[0] - self.current_phi_val[1]) / self.specimen_parameter[0] * 100
        self.current_output_param[2] = (self.current_phi_val[2] - self.current_phi_val[3] * self.specimen_parameter[5] / 1000) / 9.81 * 1000 / self.specimen_parameter[6] / 1000
        self.current_output_param[3] = self.current_phi_val[3] * self.specimen_parameter[5] / 1000 / 9.81 / 0.998223
        self.current_output_param[4] = (self.current_output_param[2] - self.current_output_param[3]) / self.current_output_param[3] * 100
        
        self.window.Element("current_output_param_0").Update(value="{:.6f}".format(self.current_output_param[0]))
        self.window.Element("current_output_param_1").Update(value="{:.6f}".format(self.current_output_param[1]))
        self.window.Element("current_output_param_2").Update(value="{:.6f}".format(self.current_output_param[2]))
        self.window.Element("current_output_param_3").Update(value="{:.6f}".format(self.current_output_param[3]))
        self.window.Element("current_output_param_4").Update(value="{:.6f}".format(self.current_output_param[4]))
        self.window.Element("current_output_param_5").Update(value="{:.6f}".format(self.current_output_vol * 5 / 65536))
        
    
    
    def _save_data(self):
        with open(self.save_dir, "a", newline="") as f:
            writer = csv.writer(f)
            data = [time.time() - self.start_time] + list(self.current_vol) + list(self.current_phi_val) + list(self.current_output_param)
            writer.writerow(data)
    
    
    def _import_event(self, event, values):    
        
        if "slope" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.slope[int(event[-1])] = float(values[event])


        elif "intercept" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.intercept[int(event[-1])] = float(values[event])
        
        
        elif "tare" in event:
            self.window.Element(event).Update(disabled=True)
            
            ch_num = int(event[-1])
            self.intercept[ch_num] -= self.current_phi_val[ch_num]
            
            element_key_intercept = "intercept_change_CH" + str(ch_num)
            self.window.Element(element_key_intercept).Update(value="{:.5f}".format(self.intercept[ch_num]))
            
            self.window.Element(event).Update(disabled=False)
        
        
        elif "save_interval" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.save_interval = float(values[event])
                
        elif "save_file_path" in event:
            if self.save_dir != values[event]:
                self.save_dir = values[event]
                self.window.Element("start_saving").Update(disabled=True)
                self.window.Element("stop_saving").Update(disabled=False)
                self.is_saving_allowed = True
                self.start_time = time.time()
                with open(self.save_dir, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Time(s)", 
                                     "CH0_Vol(V)", 
                                     "CH1_Vol(V)",
                                     "CH2_Vol(V)", 
                                     "CH3_Vol(V)",  
                                     "CH0_Load_Cell_(Odo)", 
                                     "CH1_Displacement_Gauge", 
                                     "CH2_Load_Cell_(Tank)", 
                                     "CH3_Hydraulic_Pressure",
                                     "sigma_a(kPa)",
                                     "epsilon_a(%)",
                                     "Discharged Volume(mm3)",
                                     "Discharged Water(mm3)",
                                     "Volume Percentage(%)"])
        
        elif "stop_saving" in event:
            self.is_saving_allowed = False
            self.window.Element("start_saving").Update(disabled=False)
            self.window.Element("stop_saving").Update(disabled=True)
        
        
        elif "start_control" in event:
            self.is_controling = True
            self.window.Element("stop_control").Update(disabled=False)
            self.window.Element("start_control").Update(disabled=True)
            self.start_time_cur_step = time.time()
        
        
        elif "stop_control" in event:
            self.is_controling = False
            self.window.Element("start_control").Update(disabled=False)
            self.window.Element("stop_control").Update(disabled=True)
        
        elif "control_option" in event:
            self.current_control_option = int(event[-1])
            self.start_time_cur_step = time.time()
        
        elif "control_param" in event:
            row_index = int(event[-3])
            col_index = int(event[-1])
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                self.control_param[row_index, col_index] = float(values[event])
    
        elif "specimen_parameter" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                param_id = int(event[-1])
                self.specimen_parameter[param_id] = float(values[event])
                
                temp_specimen_area = self.specimen_parameter[1] ** 2 * math.pi / 4
                temp_specimen_volume = temp_specimen_area * self.specimen_parameter[0]
                self.window.Element("specimen_parameter_2").update(value=temp_specimen_area)
                self.window.Element("specimen_parameter_3").update(value=temp_specimen_volume)
                
                temp_tank_area = self.specimen_parameter[4] ** 2 * math.pi / 4
                self.window.Element("specimen_parameter_5").update(value=temp_tank_area)
        
        elif "current_output_param_5" in event:
            try:
                float(values[event])
            except ValueError as e:
                print(e)
            else:
                temp = float(values[event]) / 5
                print(temp)
                
                if temp > 1:
                    temp = 1
                elif temp < 0:
                    temp = 0
                
                self.current_output_vol = int(temp * 65536)
        

    def _control_adc_output(self):
        
        ellapsed_time_cur_step = time.time() - self.start_time_cur_step
        
        if self.current_control_option == 0:
            pass
        
        # Creep
        elif self.current_control_option == 1:
            temp_control_param = self.control_param[:, 1]
            
            if ellapsed_time_cur_step > temp_control_param[1]:
                self.current_control_option = 0
                self.window.Element("control_option_0").Update(value=True)
            else:
                # the designated threshold value is σ
                if temp_control_param[0] == 0.:
                    temp_offset_stress = self.current_output_param[0] - temp_control_param[2]
                    
                    if abs(temp_offset_stress) > temp_control_param[4]:
                        self.current_output_vol -= int(sign_with_abs(temp_offset_stress) * temp_control_param[5] * self.vol_out_interval / 1000 * self.specimen_parameter[2] / self.adc_amp_factor / 5 * 65536)

                    elif abs(temp_offset_stress) > temp_control_param[3]:
                        self.current_output_vol -= int(sign_with_abs(temp_offset_stress) * temp_control_param[5] * self.vol_out_interval * (abs(temp_offset_stress) - temp_control_param[3]) / (temp_control_param[4] - temp_control_param[3]) / 1000 * self.specimen_parameter[2] / self.adc_amp_factor / 5 * 65536)
                
                # the designated threshold value is ɛ
                else:
                    temp_offset_strain = self.current_output_param[1] - temp_control_param[2]
                    temp_offset_stress = temp_offset_strain / 100 * self.base_elastic_modulus
                    
                    if abs(temp_offset_stress) > temp_control_param[4]:
                        pass
                    elif abs(temp_offset_stress) > temp_control_param[3]:
                        pass
                

                
        
        # Monotic Loading
        elif self.current_control_option == 2:
            temp_control_param = self.control_param[:, 2]
            temp_offset_stress = self.current_output_param[0] - temp_control_param[1]
            temp_offset_strain = self.current_output_param[1] - temp_control_param[2]
            
            if (temp_offset_stress > temp_control_param[4]) or (temp_offset_strain > temp_control_param[5]):
                self.current_control_option = 0
                self.window.Element("control_option_0").Update(value=True)
            else:
                if temp_control_param[0] == 0.:
                    self.current_output_vol += int(temp_control_param[3] / self.adc_amp_factor / 5 * 65536)
                else:
                    self.current_output_vol -= int(temp_control_param[3] / self.adc_amp_factor / 5 * 65536)
                
                self.dac.value = self.current_output_vol

        # Cyclic Loading
        elif self.current_control_option == 3:
            temp_control_param = self.control_param[:, 3]
            pass
    
        if self.current_output_vol > 65535:
                self.current_output_vol = 65535
        elif self.current_output_vol < 0:
            self.current_output_vol = 0
        
        self.dac.value = self.current_output_vol

            
    
def sign_with_abs(x):
    return 0.0 if abs(x) == 0 else x / abs(x)

def main():
    Window()    

if __name__ == "__main__":
    main()