"""Predefined contest templates."""

TEMPLATES = [
    {
        "template_id": "spring_damper_stiffness_loss",
        "name": "Mass-Spring-Damper Stiffness Loss",
        "description": "Forecast motion as a spring gradually loses stiffness.",
        "twin_id": "mass_spring_damper",
        "sensor_configs": [
            {"sensor_id": "position", "noise_std": 0.002},
            {"sensor_id": "velocity", "noise_std": 0.005},
            {"sensor_id": "temperature"},
        ],
        "fault_schedule": [
            {
                "fault_id": "reduced_stiffness",
                "start_time": 15.0,
                "end_time": None,
                "severity": 0.6,
            }
        ],
        "initial_conditions": {"position": 0.15, "velocity": 0.0},
        "sampling_rate_hz": 20.0,
        "task_type": "FORECASTING",
    },
    {
        "template_id": "pump_bearing_fault",
        "name": "Pump Bearing Wear",
        "description": "Detect and forecast bearing wear in an industrial pump.",
        "twin_id": "industrial_pump",
        "sensor_configs": [
            {"sensor_id": "flow_rate", "noise_std": 0.2},
            {"sensor_id": "pressure", "noise_std": 0.02},
            {"sensor_id": "temperature", "noise_std": 0.05},
            {"sensor_id": "vibration", "noise_std": 0.03},
        ],
        "fault_schedule": [
            {
                "fault_id": "bearing_wear",
                "start_time": 20.0,
                "end_time": None,
                "severity": 0.7,
            }
        ],
        "initial_conditions": {"flow_rate": 120.0, "pressure": 4.0, "wear": 0.05},
        "sampling_rate_hz": 10.0,
        "task_type": "FORECASTING",
    },
    {
        "template_id": "motor_voltage_imbalance",
        "name": "Motor Voltage Imbalance",
        "description": "Monitor a motor under an electrical imbalance fault.",
        "twin_id": "electric_motor",
        "sensor_configs": [
            {"sensor_id": "current", "noise_std": 0.05},
            {"sensor_id": "voltage", "noise_std": 0.5},
            {"sensor_id": "rotational_speed", "noise_std": 1.0},
            {"sensor_id": "temperature", "noise_std": 0.05},
        ],
        "fault_schedule": [
            {
                "fault_id": "voltage_imbalance",
                "start_time": 10.0,
                "end_time": None,
                "severity": 0.5,
            }
        ],
        "initial_conditions": {"current": 12.0, "voltage": 400.0, "speed": 1450.0},
        "sampling_rate_hz": 50.0,
        "task_type": "FORECASTING",
    },
    {
        "template_id": "gearbox_tooth_wear",
        "name": "Gearbox Tooth Wear",
        "description": "Analyze vibration and power changes from worn gear teeth.",
        "twin_id": "rotating_machinery",
        "sensor_configs": [
            {"sensor_id": "rotational_speed", "noise_std": 1.0},
            {"sensor_id": "vibration", "noise_std": 0.02},
            {"sensor_id": "temperature", "noise_std": 0.05},
            {"sensor_id": "power", "noise_std": 50.0},
        ],
        "fault_schedule": [
            {
                "fault_id": "gear_tooth_wear",
                "start_time": 25.0,
                "end_time": None,
                "severity": 0.8,
            }
        ],
        "initial_conditions": {"speed": 1800.0, "power": 75000.0},
        "sampling_rate_hz": 25.0,
        "task_type": "FORECASTING",
    },
    {
        "template_id": "building_hvac_failure",
        "name": "Smart Building HVAC Failure",
        "description": "Track indoor comfort and air quality during HVAC degradation.",
        "twin_id": "smart_building",
        "sensor_configs": [
            {"sensor_id": "temperature", "noise_std": 0.05},
            {"sensor_id": "humidity", "noise_std": 0.1},
            {"sensor_id": "co2_concentration", "noise_std": 5.0},
            {"sensor_id": "occupancy"},
        ],
        "fault_schedule": [
            {
                "fault_id": "hvac_failure",
                "start_time": 30.0,
                "end_time": None,
                "severity": 0.9,
            }
        ],
        "initial_conditions": {
            "temperature": 22.0,
            "humidity": 45.0,
            "co2": 650.0,
            "occupancy": 25,
        },
        "sampling_rate_hz": 2.0,
        "task_type": "FORECASTING",
    },
]


def template_summary(template: dict) -> dict:
    return {
        "template_id": template["template_id"],
        "name": template["name"],
        "description": template["description"],
        "twin_id": template["twin_id"],
        "sampling_rate_hz": template["sampling_rate_hz"],
        "task_type": template["task_type"],
    }
