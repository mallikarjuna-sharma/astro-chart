import sys, pathlib
_repo = pathlib.Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from Business_Prediction.business_engine import compute_business_prediction
from Business_Prediction.generate_business_report import (
    render_astrologer_report_html,
    render_client_report_html,
)


class _FakePayload:
    def __init__(self):
        self.dob = "1990-05-15"
        self.planet_house = {
            "Sun": 10, "Moon": 4, "Mars": 3, "Mercury": 7,
            "Jupiter": 1, "Venus": 7, "Saturn": 6, "Rahu": 7, "Ketu": 1,
        }
        self.house_lords = {
            "1": "Jupiter", "2": "Saturn", "3": "Saturn", "4": "Jupiter",
            "5": "Mars", "6": "Venus", "7": "Mars", "8": "Venus",
            "9": "Mercury", "10": "Mercury", "11": "Sun", "12": "Moon",
        }
        self.planet_dignities = {"Mercury": "OWN", "Venus": "EXALTED"}
        self.sav_points_houses = {"10": 32, "11": 33}
        self.darakaraka = "Saturn"
        self.dasha_sequence = [
            {"lord": "Mercury", "start_age": 0, "end_age": 17},
            {"lord": "Ketu", "start_age": 17, "end_age": 24},
            {"lord": "Venus", "start_age": 24, "end_age": 44},
        ]


payload = _FakePayload()
prediction = compute_business_prediction(payload, top_n_sectors=19, enable_llm_narrative=False)

assert "diversified_sectors" in prediction
assert prediction["diversified_sectors"]["diversified_top_sectors"]
print("diversified_sectors OK:", len(prediction["diversified_sectors"]["diversified_top_sectors"]), "top rows")
print("family_groups:", [g["archetype_family"] for g in prediction["diversified_sectors"]["family_groups"]])

astro_html = render_astrologer_report_html("Synthetic Audit Chart v4", prediction, payload=payload, lang="en")
client_html = render_client_report_html("Synthetic Audit Chart v4", prediction, payload=payload, lang="en")

out_dir = _repo / "Business_Prediction" / "outputs"
(out_dir / "audit_synthetic_astrologer_v4.html").write_text(astro_html, encoding="utf-8")
(out_dir / "audit_synthetic_client_v4.html").write_text(client_html, encoding="utf-8")
print("wrote v4 reports")
