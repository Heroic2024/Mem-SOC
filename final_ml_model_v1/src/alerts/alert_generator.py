import json


class AlertGenerator:

    def generate(
        self,
        attack,
        confidence,
        flow,
        top_features,
        shap_explanation=None
    ):

        alert = {
            "attack": attack,
            "confidence": round(float(confidence), 4),

            "src_port": int(flow["L4_SRC_PORT"]),
            "dst_port": int(flow["L4_DST_PORT"]),
            "protocol": int(flow["PROTOCOL"]),

            "top_features": top_features
        }

        # Add SHAP explanation if available
        if shap_explanation is not None:

            alert["shap_explanation"] = shap_explanation

        print("\n========== ALERT ==========\n")

        print(
            json.dumps(
                alert,
                indent=4
            )
        )

        return alert