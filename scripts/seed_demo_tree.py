"""Seed a realistic demo research tree for screenshots."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)

def ts(minutes_ago: int) -> str:
    return (now - timedelta(minutes=minutes_ago)).isoformat()

def evidence(content, url, title, provider="web", supports=True, conf=0.8):
    return {
        "id": f"ev{hash(content) % 99999:05d}",
        "content": content,
        "source_url": url,
        "source_title": title,
        "provider": provider,
        "supports_claim": supports,
        "confidence": conf,
        "discovered_at": ts(10),
    }

def claim(content, status, conf, urls, ev_for=None, ev_against=None, vq=None, dq=None):
    return {
        "id": f"cl{hash(content) % 99999:05d}",
        "content": content,
        "status": status,
        "confidence": conf,
        "source_urls": urls,
        "evidence_for": ev_for or [],
        "evidence_against": ev_against or [],
        "verification_query": vq,
        "deepening_question": dq,
        "created_at": ts(15),
    }

# Root branch: main investigation
root_id = "br_root_001"
verify_id = "br_verify_01"
deepen_id = "br_deepen_01"
counter_id = "br_counter_01"
deep2_id = "br_deep_002"

tree = {
    "id": "demo_fusion_2035",
    "question": "Is fusion power viable by 2035?",
    "status": "converged",
    "root_branch_id": root_id,
    "created_at": ts(30),
    "finished_at": ts(1),
    "max_depth": 4,
    "max_branch_iterations": 5,
    "verification_threshold": 0.6,
    "total_claims": 18,
    "verified_claims": 8,
    "refuted_claims": 2,
    "contested_claims": 3,
    "total_evidence": 34,
    "total_sources": 22,
    "llm_prompt_tokens": 487320,
    "llm_completion_tokens": 52840,
    "llm_requests": 47,
    "pages_fetched": 38,
    "synthesis": json.dumps({
        "title": "Fusion Power Viability Assessment: 2035 Outlook",
        "summary": "Commercial fusion power by 2035 remains unlikely but several milestones are on track. NIF achieved ignition in 2022, ITER construction continues with delays, and private companies like Commonwealth Fusion Systems are making progress with high-temperature superconducting magnets. The primary bottlenecks are tritium supply, plasma stability at scale, and the engineering gap between scientific breakeven and net electricity generation.",
        "sections": [
            {"heading": "Scientific Progress", "body": "The NIF ignition achievement in December 2022 demonstrated that fusion energy gain is physically possible. ITER, despite delays, remains the flagship international project targeting first plasma by 2035. Multiple private ventures have achieved significant milestones.", "confidence": 0.92, "citations": ["https://www.nature.com/articles/d41586-022-04440-7"]},
            {"heading": "Engineering Challenges", "body": "Three major engineering hurdles remain: tritium fuel supply (contested — breeding blankets may solve this), first-wall materials that can withstand 14 MeV neutrons, and sustained plasma control at reactor scale.", "confidence": 0.78, "citations": ["https://www.science.org/doi/10.1126/science.add7439"]},
            {"heading": "Economic Outlook", "body": "Current projections put fusion LCOE at $50-100/MWh if technical challenges are solved, competitive with other clean energy sources. However, no fusion device has yet produced net electricity.", "confidence": 0.65, "citations": ["https://www.iea.org/reports/fusion-energy"]},
        ],
        "verified_conclusions": [
            "NIF achieved fusion ignition on December 5, 2022",
            "ITER first plasma target is 2035 (delayed from 2025)",
            "Commonwealth Fusion Systems raised $1.8B and targets 2030s for ARC reactor",
            "No fusion device has produced net electricity as of 2024",
        ],
        "contested_points": [
            "Whether tritium supply is a fundamental bottleneck or solvable via breeding blankets",
            "Timeline for ITER completion given historical delays",
            "Cost projections for commercial fusion plants",
        ],
        "open_questions": [
            "Can high-temperature superconducting magnets scale to reactor size?",
            "What is the realistic LCOE for first-generation fusion plants?",
            "Will regulatory frameworks for fusion plants be ready by 2035?",
        ],
        "confidence_overall": 0.72,
    }),
    "branches": {
        root_id: {
            "id": root_id,
            "question": "Is fusion power viable by 2035?",
            "branch_type": "investigation",
            "parent_branch_id": None,
            "parent_claim_id": None,
            "depth": 0,
            "iteration": 4,
            "max_iterations": 5,
            "converged": True,
            "convergence_reason": "LLM assessment: coverage=87%",
            "created_at": ts(30),
            "finished_at": ts(8),
            "urls_searched": 42,
            "pages_fetched": 18,
            "queries_used": [
                "fusion power viability 2035",
                "ITER construction progress timeline",
                "private fusion companies funding 2024",
                "fusion energy engineering challenges remaining",
                "NIF ignition results implications commercial fusion",
                "fusion tritium supply bottleneck solutions",
                "fusion LCOE cost projection",
            ],
            "child_branch_ids": [verify_id, deepen_id, counter_id],
            "claims": [
                claim("NIF achieved fusion ignition on December 5, 2022, producing 3.15 MJ from 2.05 MJ of laser energy", "verified", 0.95,
                      ["https://www.nature.com/articles/d41586-022-04440-7", "https://www.llnl.gov/news/shot"],
                      ev_for=[
                          evidence("NIF ignition confirmed", "https://www.nature.com/articles/d41586-022-04440-7", "Nature: NIF Ignition"),
                          evidence("LLNL official announcement of fusion ignition", "https://www.llnl.gov/news/shot", "LLNL Announcement"),
                          evidence("DOE confirms NIF result", "https://www.energy.gov/articles/fusion-breakthrough", "DOE Fusion Breakthrough"),
                      ]),
                claim("ITER first plasma target has been delayed to 2035, from original 2025 schedule", "verified", 0.88,
                      ["https://www.iter.org/proj/inafewlines", "https://www.science.org/content/article/iter-delays"],
                      ev_for=[
                          evidence("ITER timeline update", "https://www.iter.org/proj/inafewlines", "ITER Official"),
                          evidence("Science reports ITER delays", "https://www.science.org/content/article/iter-delays", "Science Magazine"),
                      ]),
                claim("Commonwealth Fusion Systems raised $1.8B in Series B funding and targets ARC reactor in 2030s", "verified", 0.90,
                      ["https://cfs.energy/news/series-b", "https://www.bloomberg.com/news/cfs-fusion"],
                      ev_for=[
                          evidence("CFS Series B announcement", "https://cfs.energy/news/series-b", "CFS Official"),
                          evidence("Bloomberg coverage of CFS funding", "https://www.bloomberg.com/news/cfs-fusion", "Bloomberg"),
                      ]),
                claim("Tritium supply is a critical bottleneck for fusion reactors — global supply only ~25 kg", "contested", 0.55,
                      ["https://www.science.org/doi/10.1126/science.tritium"],
                      ev_for=[evidence("Tritium scarcity analysis", "https://www.science.org/doi/10.1126/science.tritium", "Science")],
                      ev_against=[evidence("Breeding blankets can produce tritium in-situ", "https://www.nature.com/articles/tritium-breeding", "Nature Energy")]),
                claim("No fusion device has yet produced net electricity delivered to a grid", "accepted", 0.95,
                      ["https://www.iaea.org/topics/energy/fusion/status"],
                      ev_for=[evidence("IAEA fusion status report", "https://www.iaea.org/topics/energy/fusion/status", "IAEA")]),
                claim("TAE Technologies claims to have achieved plasma temperatures of 75 million degrees", "verified", 0.82,
                      ["https://tae.com/news/milestone", "https://www.reuters.com/technology/tae-fusion"],
                      ev_for=[
                          evidence("TAE milestone announcement", "https://tae.com/news/milestone", "TAE Technologies"),
                          evidence("Reuters reports on TAE progress", "https://www.reuters.com/technology/tae-fusion", "Reuters"),
                      ]),
                claim("Fusion LCOE projected at $50-100/MWh according to IEA analysis", "accepted", 0.70,
                      ["https://www.iea.org/reports/fusion-energy"],
                      ev_for=[evidence("IEA fusion cost analysis", "https://www.iea.org/reports/fusion-energy", "IEA")],
                      dq="What is the realistic $/MWh projection for first-generation fusion?"),
                claim("Helion Energy signed PPA with Microsoft for fusion electricity by 2028", "verified", 0.85,
                      ["https://www.helionenergy.com/news/microsoft-ppa", "https://www.cnbc.com/helion-microsoft"],
                      ev_for=[
                          evidence("Helion PPA announcement", "https://www.helionenergy.com/news/microsoft-ppa", "Helion"),
                          evidence("CNBC coverage", "https://www.cnbc.com/helion-microsoft", "CNBC"),
                      ]),
            ],
        },
        verify_id: {
            "id": verify_id,
            "question": "Verify: ITER first plasma target has been delayed to 2035",
            "branch_type": "verification",
            "parent_branch_id": root_id,
            "parent_claim_id": f"cl{hash('ITER first plasma target has been delayed to 2035, from original 2025 schedule') % 99999:05d}",
            "depth": 1,
            "iteration": 2,
            "max_iterations": 2,
            "converged": True,
            "convergence_reason": "No new claims found — saturated",
            "created_at": ts(20),
            "finished_at": ts(15),
            "urls_searched": 8,
            "pages_fetched": 5,
            "queries_used": ["ITER construction delay 2035 first plasma", "ITER project timeline update 2024"],
            "child_branch_ids": [],
            "claims": [
                claim("ITER Council confirmed revised baseline schedule targeting first plasma in 2035", "accepted", 0.90,
                      ["https://www.iter.org/council-decisions"],
                      ev_for=[evidence("ITER Council meeting minutes", "https://www.iter.org/council-decisions", "ITER Organization")]),
                claim("Original ITER first plasma target was 2025, cost overruns caused delays", "accepted", 0.85,
                      ["https://www.world-nuclear.org/information-library/iter"],
                      ev_for=[evidence("WNA ITER overview", "https://www.world-nuclear.org/information-library/iter", "World Nuclear Association")]),
            ],
        },
        deepen_id: {
            "id": deepen_id,
            "question": "What are the specific engineering challenges preventing commercial fusion before 2035?",
            "branch_type": "deepening",
            "parent_branch_id": root_id,
            "parent_claim_id": None,
            "depth": 1,
            "iteration": 3,
            "max_iterations": 5,
            "converged": True,
            "convergence_reason": "Diminishing returns: 1 new / 5 total (20%)",
            "created_at": ts(18),
            "finished_at": ts(10),
            "urls_searched": 15,
            "pages_fetched": 9,
            "queries_used": [
                "fusion reactor engineering challenges 2024",
                "plasma facing materials fusion neutron damage",
                "tokamak plasma instability control",
                "fusion fuel cycle tritium breeding blanket",
            ],
            "child_branch_ids": [deep2_id],
            "claims": [
                claim("First-wall materials must withstand 14 MeV neutron bombardment — no existing material lasts >2 years", "verified", 0.80,
                      ["https://www.nature.com/articles/materials-fusion", "https://www.ornl.gov/fusion-materials"],
                      ev_for=[
                          evidence("Nature materials review", "https://www.nature.com/articles/materials-fusion", "Nature"),
                          evidence("ORNL fusion materials program", "https://www.ornl.gov/fusion-materials", "ORNL"),
                      ]),
                claim("Plasma disruptions in tokamaks can deposit 10+ MJ/m² on vessel walls in milliseconds", "accepted", 0.85,
                      ["https://www.euro-fusion.org/news/disruptions"],
                      ev_for=[evidence("EUROfusion disruption research", "https://www.euro-fusion.org/news/disruptions", "EUROfusion")]),
                claim("High-temperature superconducting (HTS) magnets enable smaller, cheaper reactors", "verified", 0.88,
                      ["https://news.mit.edu/2021/MIT-CFS-fusion-magnet-0905", "https://www.nature.com/articles/hts-magnets-fusion"],
                      ev_for=[
                          evidence("MIT/CFS HTS magnet demonstration", "https://news.mit.edu/2021/MIT-CFS-fusion-magnet-0905", "MIT News"),
                          evidence("Nature HTS review", "https://www.nature.com/articles/hts-magnets-fusion", "Nature"),
                      ]),
                claim("Stellarator designs (Wendelstein 7-X) avoid plasma disruptions entirely but are harder to build", "accepted", 0.78,
                      ["https://www.ipp.mpg.de/w7x"],
                      ev_for=[evidence("W7-X overview", "https://www.ipp.mpg.de/w7x", "Max Planck IPP")]),
                claim("Remote maintenance of activated fusion components requires robotics that don't yet exist at scale", "pending", 0.60,
                      ["https://www.ukaea.uk/programmes/remote-maintenance"],
                      ev_for=[evidence("UKAEA RACE program", "https://www.ukaea.uk/programmes/remote-maintenance", "UKAEA")],
                      vq="fusion reactor remote maintenance robotics UKAEA RACE"),
            ],
        },
        counter_id: {
            "id": counter_id,
            "question": "Counter-evidence: Tritium supply is a critical bottleneck for fusion reactors",
            "branch_type": "counter",
            "parent_branch_id": root_id,
            "parent_claim_id": f"cl{hash('Tritium supply is a critical bottleneck for fusion reactors — global supply only ~25 kg') % 99999:05d}",
            "depth": 1,
            "iteration": 2,
            "max_iterations": 2,
            "converged": True,
            "convergence_reason": "No new claims found — saturated",
            "created_at": ts(16),
            "finished_at": ts(12),
            "urls_searched": 6,
            "pages_fetched": 4,
            "queries_used": ["tritium breeding blanket fusion self-sufficient", "lithium tritium production fusion reactor"],
            "child_branch_ids": [],
            "claims": [
                claim("Lithium breeding blankets can theoretically produce more tritium than consumed (TBR > 1)", "accepted", 0.75,
                      ["https://www.nature.com/articles/tritium-breeding"],
                      ev_for=[evidence("Tritium breeding ratio analysis", "https://www.nature.com/articles/tritium-breeding", "Nature Energy")]),
                claim("ITER's test blanket module program will validate tritium breeding in 2030s", "accepted", 0.70,
                      ["https://www.iter.org/mach/TritiumBreeding"],
                      ev_for=[evidence("ITER TBM program", "https://www.iter.org/mach/TritiumBreeding", "ITER")]),
                claim("Canadian CANDU reactors currently produce most of world's tritium supply as byproduct", "verified", 0.88,
                      ["https://www.opg.com/tritium", "https://www.world-nuclear.org/tritium"],
                      ev_for=[
                          evidence("OPG tritium production", "https://www.opg.com/tritium", "Ontario Power Generation"),
                          evidence("WNA tritium overview", "https://www.world-nuclear.org/tritium", "World Nuclear Association"),
                      ]),
            ],
        },
        deep2_id: {
            "id": deep2_id,
            "question": "Can high-temperature superconducting magnets scale to commercial reactor size?",
            "branch_type": "deepening",
            "parent_branch_id": deepen_id,
            "parent_claim_id": f"cl{hash('High-temperature superconducting (HTS) magnets enable smaller, cheaper reactors') % 99999:05d}",
            "depth": 2,
            "iteration": 2,
            "max_iterations": 5,
            "converged": True,
            "convergence_reason": "Diminishing returns: 0 new / 3 total (0%)",
            "created_at": ts(12),
            "finished_at": ts(8),
            "urls_searched": 6,
            "pages_fetched": 4,
            "queries_used": ["REBCO HTS magnet scaling fusion reactor", "Commonwealth Fusion SPARC magnet size"],
            "child_branch_ids": [],
            "claims": [
                claim("CFS demonstrated 20-tesla HTS magnet in 2021 — largest fusion-class HTS magnet ever built", "verified", 0.92,
                      ["https://news.mit.edu/2021/MIT-CFS-fusion-magnet-0905", "https://cfs.energy/technology"],
                      ev_for=[
                          evidence("MIT/CFS magnet record", "https://news.mit.edu/2021/MIT-CFS-fusion-magnet-0905", "MIT News"),
                          evidence("CFS technology page", "https://cfs.energy/technology", "CFS"),
                      ]),
                claim("REBCO tape production capacity needs 10x increase for commercial fusion deployment", "accepted", 0.72,
                      ["https://www.superconductor-tech.com/rebco-scaling"],
                      ev_for=[evidence("REBCO scaling analysis", "https://www.superconductor-tech.com/rebco-scaling", "Superconductor Tech Review")]),
                claim("Tokamak Energy achieved 100 million degrees in ST40 spherical tokamak using HTS magnets", "verified", 0.85,
                      ["https://www.tokamakenergy.co.uk/news/100m-degrees", "https://www.bbc.com/news/tokamak-energy"],
                      ev_for=[
                          evidence("TE milestone", "https://www.tokamakenergy.co.uk/news/100m-degrees", "Tokamak Energy"),
                          evidence("BBC coverage", "https://www.bbc.com/news/tokamak-energy", "BBC"),
                      ]),
            ],
        },
    },
}

out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"{tree['id']}.json"
out_path.write_text(json.dumps(tree, indent=2))
print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
