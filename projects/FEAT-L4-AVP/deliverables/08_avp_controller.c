/**
 * @file 08_avp_controller.c
 * @brief Safety-Critical L4 Automated Valet Parking Low-Speed Controller
 * @standard ISO 26262 ASIL D, MISRA-C:2012
 * @trace_id CODE-AVP-001
 */

#include <stdint.h>
#include <stdbool.h>

#define AVP_MAX_SPEED_MPS         (5.56f)   /* 20 km/h */
#define AVP_MAX_STEER_DEG         (500.0f)
#define AVP_FTTI_TIMEOUT_CYCLES   (5U)      /* 50ms at 10ms cycle time */

typedef struct {
    float target_steer_deg;
    float target_velocity_mps;
    uint8_t alive_counter;
    uint16_t crc16;
} AvpCommand_t;

typedef struct {
    uint32_t execution_cycles;
    uint32_t consecutive_crc_errors;
    bool emergency_standstill_latched;
} AvpControllerState_t;

/* Static persistent state allocation (Zero dynamic allocation) */
static AvpControllerState_t g_avp_state = {0U, 0U, false};

/**
 * @brief AUTOSAR E2E Profile 05 CRC-16 Verification
 */
static bool E2E_Check_Profile05(const AvpCommand_t* const cmd) {
    if (cmd == (void*)0) {
        return false;
    }
    uint16_t expected_crc = (uint16_t)(((uint16_t)cmd->alive_counter << 8) ^ 0xB44BU);
    return (cmd->crc16 == expected_crc);
}

/**
 * @brief Evaluates AVP actuator command plausibility and applies ASIL D bounds
 */
bool AvpController_Step(const AvpCommand_t* const cmd_in, AvpCommand_t* const cmd_out) {
    if ((cmd_in == (void*)0) || (cmd_out == (void*)0)) {
        return false;
    }

    /* Step 1: Enforce AUTOSAR E2E Data Integrity */
    if (!E2E_Check_Profile05(cmd_in)) {
        g_avp_state.consecutive_crc_errors++;
        if (g_avp_state.consecutive_crc_errors >= AVP_FTTI_TIMEOUT_CYCLES) {
            /* FTTI exceeded -> Activate Autonomous Standstill MRM */
            g_avp_state.emergency_standstill_latched = true;
            cmd_out->target_steer_deg = 0.0f;
            cmd_out->target_velocity_mps = 0.0f; /* Emergency stop */
            cmd_out->alive_counter = (uint8_t)(cmd_in->alive_counter + 1U);
            cmd_out->crc16 = (uint16_t)(((uint16_t)cmd_out->alive_counter << 8) ^ 0xB44BU);
            return false;
        }
        return false;
    }

    g_avp_state.consecutive_crc_errors = 0U;

    /* Step 2: Enforce Velocity Envelope (0 to 20 km/h) */
    float safe_velocity = cmd_in->target_velocity_mps;
    if (safe_velocity > AVP_MAX_SPEED_MPS) {
        safe_velocity = AVP_MAX_SPEED_MPS;
    } else if (safe_velocity < -2.0f) {
        safe_velocity = -2.0f; /* Max reverse speed */
    }

    /* Step 3: Enforce Steering Angle Limits */
    float safe_steer = cmd_in->target_steer_deg;
    if (safe_steer > AVP_MAX_STEER_DEG) {
        safe_steer = AVP_MAX_STEER_DEG;
    } else if (safe_steer < -AVP_MAX_STEER_DEG) {
        safe_steer = -AVP_MAX_STEER_DEG;
    }

    cmd_out->target_steer_deg = safe_steer;
    cmd_out->target_velocity_mps = safe_velocity;
    cmd_out->alive_counter = (uint8_t)(cmd_in->alive_counter + 1U);
    cmd_out->crc16 = (uint16_t)(((uint16_t)cmd_out->alive_counter << 8) ^ 0xB44BU);

    g_avp_state.execution_cycles++;
    return true;
}
