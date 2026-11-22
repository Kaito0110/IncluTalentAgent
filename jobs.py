from catalog import JOBS


def match_jobs(profile):
    level = profile.get("level", "junior")
    selected_job = profile.get("jobId")
    preferences = set(profile.get("accommodations", []))
    matches = []
    for job in JOBS:
        level_match = job["level"] == level
        selected_match = job["id"] == selected_job
        relevant = preferences.intersection(job["supports"])
        support_fit = len(relevant) / len(preferences) if preferences else 1
        score = round((70 if level_match else 35) + support_fit * 20 + (10 if selected_match else 0))
        matches.append({
            **job,
            "match": min(score, 100),
            "matchedSupports": sorted(relevant),
            "levelMatch": level_match,
            "selectedForPractice": selected_match,
        })
    return sorted(matches, key=lambda job: (-job["match"], job["title"]))
