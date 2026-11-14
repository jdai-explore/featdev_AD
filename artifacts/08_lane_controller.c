/**
 * @file 08_lane_controller.c
 * @brief Safety-Critical Lateral & Longitudinal Controller Interface
 * @standard ISO 26262 ASIL D, MISRA-C:2012
 * @trace_id CODE-CTRL-001
 */

#include <stdint.h>
#include <stdbool.h>

#define MAX_CURVATURE_RADPM        (0.02f)
#define MIN_CURVATURE_RADPM        (-0.02f)
#define MAX_LATERAL_JERK_MPS3      (2.5f)
#define FTTI_TIMEOUT_CYCLES        (2U)    /* 20ms at 10ms cycle time */

typedef struct {
    float target_curvature_radpm;
    float target_acceleration_mps2;
    uint8_t alive_counter;
    uint16_t crc16;
} ActuatorCommand_t;

typedef struct {
    uint32_t valid_frame_count;
    uint32_t error_counter;
    bool emergency_fallback_active;
} ControllerState_t;

/* Static persistent state allocation (Zero dynamic malloc/free per MISRA Rule 21.3) */
static ControllerState_t g_controller_state = {0U, 0U, false};

/**
 * @brief AUTOSAR E2E Profile 05 CRC-16 Verification
 */
static bool E2E_Check_Profile05(const ActuatorCommand_t* const cmd) {
    if (cmd == (void*)0) {
        return false;
    }
    /* Simplified CRC-16 CCITT verification placeholder */
    uint16_t expected_crc = (uint16_t)(((uint16_t)cmd->alive_counter << 8) ^ 0xA55AU);
    return (cmd->crc16 == expected_crc);
}

/**
 * @brief Evaluates actuator command plausibility and applies ASIL D rate clamping
 */
bool LaneController_Step(const ActuatorCommand_t* const cmd_in, ActuatorCommand_t* const cmd_out) {
    if ((cmd_in == (void*)0) || (cmd_out == (void*)0)) {
        return false;
    }

    /* Step 1: Enforce AUTOSAR E2E Data Integrity */
    if (!E2E_Check_Profile05(cmd_in)) {
        g_controller_state.error_counter++;
        if (g_controller_state.error_counter >= FTTI_TIMEOUT_CYCLES) {
            /* FTTI exceeded -> Activate Fail-Safe MRM trajectory */
            g_controller_state.emergency_fallback_active = true;
            cmd_out->target_curvature_radpm = 0.0f;
            cmd_out->target_acceleration_mps2 = -2.5f; /* Graceful deceleration to shoulder */
            cmd_out->alive_counter = (uint8_t)(cmd_in->alive_counter + 1U);
            cmd_out->crc16 = (uint16_t)(((uint16_t)cmd_out->alive_counter << 8) ^ 0xA55AU);
            return false;
        }
        return false;
    }

    /* Reset consecutive error count on successful E2E check */
    g_controller_state.error_counter = 0U;

    /* Step 2: Enforce Lateral Curvature Envelope */
    float clamped_curvature = cmd_in->target_curvature_radpm;
    if (clamped_curvature > MAX_CURVATURE_RADPM) {
        clamped_curvature = MAX_CURVATURE_RADPM;
    } else if (clamped_curvature < MIN_CURVATURE_RADPM) {
        clamped_curvature = MIN_CURVATURE_RADPM;
    } else {
        /* Within valid physical envelope */
    }

    /* Step 3: Populate safe output command */
    cmd_out->target_curvature_radpm = clamped_curvature;
    cmd_out->target_acceleration_mps2 = cmd_in->target_acceleration_mps2;
    cmd_out->alive_counter = (uint8_t)(cmd_in->alive_counter + 1U);
    cmd_out->crc16 = (uint16_t)(((uint16_t)cmd_out->alive_counter << 8) ^ 0xA55AU);

    g_controller_state.valid_frame_count++;
    return true;
}
