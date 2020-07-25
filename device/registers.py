from enum import IntEnum

from flags import Flags


class ControllerCSR(Flags):
    temperature_protection = 0x1
    low_voltage_error = 0x2
    base_voltage_error = 0x4
    high_voltage_protection_active = 0x8


class ControllerRegister(IntEnum):
    cell_id = 0x00
    """ (readonly) controller ID ‐ constant 0x800e"""

    status = 0x01
    """
    (readonly) status register\n
    status[0] ‐ Temperature status; 0‐OK 1‐Temperature protection.\n
    status[1] ‐ LV error (0‐> OK)\n
    status[2] ‐ BV error (0‐> OK)\n
    status[3] ‐ HV protection active (0 ‐> No HV protection)\n
    """

    BVON = 0x02
    """ (read write) BVON register switches ON (1) and off (0) Base Voltage of the controller"""

    Tup = 0x03
    """ (readonly) Temperature of uP"""

    Tbrd = 0x04
    """ (readonly) Temperature of board sensor"""

    Tps = 0x05
    """ (readonly) Temperature of power supply sensor"""

    LV = 0x06
    """ (readonly) LV (Volt*10)"""

    BV = 0x07
    """ (readonly) BV (Volt*10)"""

    T_fan_off = 0x10
    """ (read write) T_fan_off Temperature (grad C) to switch off the module FAN"""

    T_fan_on = 0x11
    """ (read write) T_fan_on Temperature (grad C) to switch on the module FAN"""

    T_shutdown = 0x12
    """ (read write) T_shutdown Temperature (grad C) to switch off cells."""

    LVll = 0x13
    """ (read write) LV absolute value lower limit (same units as readout from addr.0x6)"""

    LVul = 0x14
    """ (read write) LV absolute value upper limit"""

    BVll = 0x15
    """ (read write) BV absolute value lower limit (same units as readout from addr.0x7)"""

    BVul = 0x16
    """ (read write) BV absolute value upper limit"""

    ccrc = 0x17
    """ (read write) ccrc ‐ Check CommandCode ‐ perform crc check on transmitted data if(ccrc != 0)"""

    NTsens = 0x18
    """ (read write) NTsens ‐ which T sensor use for temperature controll (0‐>uP, 1‐>board, 2‐>Power Supply)"""

    CserNr = 0x19
    """ (readonly) controller serial Nr."""

    WrFlash = 0x1f
    """(write only) WrFlash ‐ writing to this address will store ALL"""


class CellCSR(Flags):
    channel_on_state = 0x1
    error = 0x2
    accumulated_error = 0x4
    current_overload = 0x8
    base_voltage_error = 0x10
    hardware_failure_error = 0x20
    ramp_up_active = 0x40
    ramp_down_active = 0x80
    standby = 0x100
    io_protection = 0x200


class CellRegister(IntEnum):
    cell_id = 0
    """ (read/write) cell_id"""

    ctl_stat = 1
    """
    (read/write) used to Control a cell(channel) and check its Status\n
    chons   bit 0   chanel on bit ‐ controls and reflects on/off state of the cell. 1‐>on\n
    err     bit 1   cell error bit; 1‐>error .\n
    acerr   bit 2   cell accumulated Error (since last read) bit\n
    iovld   bit 3   I overload bit; 0 ‐> output current is OK i.e. NO current limiting regime\n
    bverr   bit 4   Base Voltage error\n
    hwerr   bit 5   Hardware failure error bit\n
    rdab    bit 6   ramp down active bit\n
    ruab    bit 7   ramp up active bit\n
    sbyb    bit 8   standby bit\n
    iopb    bit 9   ioprot bit (cleared by writing [new] Vset and on switching on HV )
    """

    VsetON = 2
    """ (read/write) set Voltage in DAC bits (12 bit)"""

    Vmes = 3
    """ (read only) measured output Voltage in ADC bits (12 bit)"""

    Iset = 4
    """ (read/write) Current Limit setpoint in DAC bits (10 bit)"""

    Imes = 5
    """ (read only) Measured Current in ADC bits (12 bit)"""

    Ustdby = 6
    """ (read/write) Voltage value in DAC bits for STanDBY regime"""

    rupspeed = 7
    """ (read/write) Speed of U ramp up (Volt/sec)"""

    rdwnspeed = 8
    """ (read/write) Speed of U ramp down (Volt/sec)"""

    prottim = 9
    """ (read/write) Delay to switch STanDBY voltage after IOVLD"""

    Umin = 10
    """ (read/write) Real output voltage (Volt) at 0 dac data"""

    Umax = 11
    """ (read/write) Real output voltage (Volt) at maximal dac data"""

    Imax = 12
    """ (read/write) Real value of current threshold limit (uA) at maximal dac data"""

    Umesmax = 13
    """ (read/write) Calculated(calibrated) value (Volt) coresponding to maximal ADC value"""

    Imesmax = 14
    """ (read/write) Calculated(calibrated) value (uA) coresponding to maximal ADC value"""

    """ (read only)
    (0x8000 | 12<<8 | 10<<4 | 12) ; minus‐>0x8000; 12<<8‐>12 ADC bits; 10<<4‐>10 I_DAC bits; 12‐>12 U_DAC bits;"""
    MINUS_n_BITS = 15
    UOKmin = 16
    """ (read/write) Lower error threshold of the cell (do not change!)"""

    UOKmax = 17
    """ (read/write) Upper error threshold of the cell (do not change!)"""

    IOKmin = 18
    """ (read/write) Error threshold of the current limiting scheme (do not change!)"""

    BVOKmin = 19
    """ (read/write) Lower error threshold of the Base Voltage power supply for the cell (do not change!)"""

    ccrc = 20
    """ (read/write) ccrc ‐ Check CommandCode ‐ perform crc check on transmitted data if(ccrc!=0)"""

    keepVset = 21
    """ (read/write) keepVset. if(keepVset!=0) On change VsetON value will be stored in eeprom and restored on boot."""

    ONonBOOT = 22
    """ (read/write) ONonBOOT ‐ if(ONonBOOT!=0) the cell turn on HV on power ON (used in standalone mode)"""

    HVOFFonIOPB = 23
    """ (read/write) HVOFFonIOPB ‐ the cell turn off HV if I overload protection fired"""

    Imes2 = 24
    """ (read only) Measured Current ‐ Second rough channel in ADC bits (12 bit)"""

    Imes2max = 25
    """ (read/write) calculated(calibrated) value (uA) coresponding to maximal ADC value for the second rough channel"""
