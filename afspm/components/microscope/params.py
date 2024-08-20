"""Holds a mapping of get/set params and descriptions.

This is particularly the param id *as we would call it from within afspm*.
The purpose is to abstract away setting specifics, so that we can use the
same param id for multiple different microscope translators.

In this file, we have a map of param_ids with descriptions. Each microscope
translator will have their own params map, mapping a param_id to a method
to receive it.

Note the lack of units in our descriptions. When a get-param is sent, no
units are specified; the response contains the value and its units (as stored
by the MicroscopeTranslator instance). When a set-param is sent, the units of the
values are passed along with it. In both cases, the person receiving the
message is responsible for converting to their internal reference units.
"""

from enum import Enum


class MicroscopeParameter(str, Enum):
    """Holds parameters that can be set."""

    # Note: Rest of Z Control Feedback is in feedback_pb2 message.
    ZCTRL_FB_SETPOINT = 'zctrl-fb-setpoint'
    ZCTRL_FB_ERRORGAIN = 'zctrl-fb-errorgain'

    TIP_BIAS_VOLTAGE = 'tip-bias-voltage'
    TIP_VIBRATING_AMPL = 'tip-vibrating-ampl'
    TIP_VIBRATING_FREQ = 'tip-vibrating-freq'

    AMPL_FB_ENABLED = 'ampl-fb-enabled'
    AMPL_FB_SETPOINT = 'ampl-fb-setpoint'
    AMPL_FB_PGAIN = 'ampl-fb-pgain'
    AMPL_FB_IGAIN = 'ampl-fb-igain'

    PLL_FB_ENABLED = 'freq-fb-enabled'
    PLL_FB_SETPOINT = 'freq-fb-setpoint'
    PLL_FB_PGAIN = 'freq-fb-pgain'
    PLL_FB_IGAIN = 'freq-fb-igain'

    SCAN_SPEED = 'scan-speed'


DESCRIPTIONS = {
    # Note: Rest of Z Control Feedback is in feedback_pb2 message.
    MicroscopeParameter.ZCTRL_FB_SETPOINT:
    "Set point of z-controller feedback.",
    MicroscopeParameter.ZCTRL_FB_ERRORGAIN:
    "Gain applied to error b/w input signal and setpoint, before feeding to"
    "PI controller.",

    MicroscopeParameter.TIP_BIAS_VOLTAGE:
    "Bias voltage applied to the tip.",
    MicroscopeParameter.TIP_VIBRATING_AMPL:
    "Free amplitude of the cantilever.",
    MicroscopeParameter.TIP_VIBRATING_FREQ: "Free frequency of the cantilever.",

    # Amplitude Feedback
    MicroscopeParameter.AMPL_FB_ENABLED:
    "Whether or not the amplitude feedback is on.",
    MicroscopeParameter.AMPL_FB_SETPOINT:
    "Amplitude setpoint.",
    MicroscopeParameter.AMPL_FB_PGAIN:
    "Gain of the proportional component.",
    MicroscopeParameter.AMPL_FB_IGAIN:
    "Gain of the integral component.",

    # Frequency Modulation
    MicroscopeParameter.PLL_FB_ENABLED:
    "Whether or not the frequency feedback is on.",
    MicroscopeParameter.PLL_FB_SETPOINT:
    "Frequency setpoint.",
    MicroscopeParameter.PLL_FB_PGAIN:
    "Gain of the proportional component.",
    MicroscopeParameter.PLL_FB_IGAIN:
    "Gain of the integral component.",
    MicroscopeParameter.SCAN_SPEED:
    "Speed at which scanning occurs."
}


class ParameterError(Exception):
    """Translator failed at getting or setting a parameter."""

    pass
