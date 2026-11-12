"""Data every dashboard page can read, built once per run by the sidebar."""

from dataclasses import dataclass


@dataclass
class AppContext:
    menu: str
    all_papers: list
    papers: list
    selected_faculty_id: str
    faculty_list: list
    faculty_options: list
    faculty_labels: dict
    total_all: int
    total_active: int
    total_analyzed: int
    fac_dist: dict
