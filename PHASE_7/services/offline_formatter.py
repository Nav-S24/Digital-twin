class OfflineFormatter:

    @staticmethod
    def format(intent: str, context: dict) -> str:

        vehicle = context.get("vehicle_context")
        diagnostic = context.get("diagnostic_context", [])
        error = context.get("vehicle_error")

        if error:
            return f"⚠ {error}"

        # ---------------- HEALTH ----------------

        if intent == "HEALTH_EXPLANATION" and vehicle:

            return f"""
🚗 Vehicle Health Report

Vehicle ID: {vehicle['Vehicle_ID']}

Overall Vehicle Health:
{vehicle['vehicle_health']}

Health Category:
{vehicle['health_class']}

Engine Health:
{vehicle['engine_health']}

Battery Health:
{vehicle['battery_health']}

ML Health Score:
{vehicle['ml_health_score']}

Highest Risk Sensor:
{vehicle['Top_Risk_Sensor']}

Affected System:
{vehicle['Affected_System']}

Explanation:
{vehicle['Reason']}
""".strip()

        # ---------------- FAILURE RISK ----------------

        if intent == "FAILURE_RISK" and vehicle:

            return f"""
⚠ Failure Risk Assessment

Vehicle ID:
{vehicle['Vehicle_ID']}

Failure Probability:
{vehicle['Failure_Probability']}

Failure Risk:
{vehicle['Failure_Risk_Percentage']}

Highest Risk Sensor:
{vehicle['Top_Risk_Sensor']}

Affected System:
{vehicle['Affected_System']}

Reason:
{vehicle['Reason']}

Urgency:
{vehicle['Urgency']}
""".strip()

        # ---------------- RUL ----------------

        if intent == "RUL_QUERY" and vehicle:

            return f"""
⏳ Remaining Useful Life

Vehicle:
{vehicle['Vehicle_ID']}

Remaining Life:
{vehicle['Remaining_Useful_Life_Cycles']} cycles

Approximate Distance:
{vehicle['Remaining_Useful_Life_KM']} km

Book Service Within:
{vehicle['Book_Service_Within_Days']} days

Urgency:
{vehicle['Urgency']}
""".strip()

        # ---------------- MAINTENANCE ----------------

        if intent == "MAINTENANCE_QUERY" and vehicle:

            text = f"""
🔧 Maintenance Recommendation

Vehicle:
{vehicle['Vehicle_ID']}

Priority:
{vehicle['Maintenance_Priority']}

Recommended Action:
{vehicle['Recommended_Action']}

Affected System:
{vehicle['Affected_System']}

Reason:
{vehicle['Reason']}

Book Service Within:
{vehicle['Book_Service_Within_Days']} days
"""

            if diagnostic:

                d = diagnostic[0]["data"]

                text += f"""

----------------------------------

Diagnostic Code:
{d['code']}

Description:
{d['description']}

Driver Advice:
{d['driver_advice']}
"""

            return text.strip()

        # ---------------- FAULT ----------------

        if intent == "FAULT_DIAGNOSIS" and diagnostic:

            d = diagnostic[0]["data"]

            return f"""
🔧 Fault Diagnosis

Code:
{d['code']}

Description:
{d['description']}

Severity:
{d['severity']}

Failure Risk:
{d['failure_risk']}

Remaining Life:
{d['remaining_life_pct']}%

Recommendation:
{d['recommendation']}

Driver Advice:
{d['driver_advice']}

Estimated Repair Window:
{d['estimated_repair_window']}
""".strip()

        # ---------------- DRIVING SAFETY ----------------

        if intent == "DRIVING_SAFETY":

            answer = ""

            if diagnostic:

                d = diagnostic[0]["data"]

                answer += f"""
🚗 Driving Safety

Trip Status:
{d['trip_status']}

Driver Advice:
{d['driver_advice']}

Failure Risk:
{d['failure_risk']}

"""

            if vehicle:

                answer += f"""

Vehicle Health:
{vehicle['vehicle_health']}

Trip Readiness:
{vehicle['trip_readiness']}

Fault Count:
{vehicle['fault_count']}

Urgency:
{vehicle['Urgency']}
"""

            return answer.strip()

        # ---------------- VEHICLE STATUS ----------------

        if intent == "VEHICLE_STATUS" and vehicle:

            return f"""
🚙 Vehicle Status

Vehicle Health:
{vehicle['vehicle_health']}

Health Category:
{vehicle['health_class']}

Trip Readiness:
{vehicle['trip_readiness']}

Fault Count:
{vehicle['fault_count']}

Urgency:
{vehicle['Urgency']}
""".strip()

        # ---------------- KNOWLEDGE ----------------

        if intent == "VEHICLE_KNOWLEDGE":

            return (
                "This is a general automotive knowledge question. "
                "Configure a Gemini API key to enable conversational AI answers. "
                "answers for general knowledge."
            )

        return "No information available."