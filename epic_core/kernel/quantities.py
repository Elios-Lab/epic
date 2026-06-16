"""Shared physical quantity ontology."""

from enum import Enum


class PhysicalQuantity(Enum):
    LINEAR_POSITION = "linear_position"
    LINEAR_VELOCITY = "linear_velocity"
    LINEAR_ACCELERATION = "linear_acceleration"

    ANGULAR_POSITION = "angular_position"
    ANGULAR_VELOCITY = "angular_velocity"
    ANGULAR_ACCELERATION = "angular_acceleration"
    ROTATIONAL_SPEED = "rotational_speed"

    TEMPERATURE = "temperature"
    HEAT_FLUX = "heat_flux"

    PRESSURE = "pressure"
    FLOW_RATE = "flow_rate"
    FLUID_LEVEL = "fluid_level"

    CURRENT = "current"
    VOLTAGE = "voltage"
    POWER = "power"
    RESISTANCE = "resistance"
    TORQUE = "torque"

    VIBRATION = "vibration"
    SOUND_PRESSURE = "sound_pressure"

    HUMIDITY = "humidity"
    ILLUMINANCE = "illuminance"
    CO2_CONCENTRATION = "co2_concentration"
    OCCUPANCY = "occupancy"

    PACKET_RATE = "packet_rate"
    LATENCY = "latency"
    CPU_UTILIZATION = "cpu_utilization"

    HEART_RATE = "heart_rate"
    BLOOD_OXYGEN = "blood_oxygen"
    ECG_SIGNAL = "ecg_signal"
