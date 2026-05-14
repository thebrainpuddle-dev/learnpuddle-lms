from __future__ import annotations

import pytest

from apps.maic.runtime_contract import (
    require_valid_classroom_runtime_contract,
    validate_classroom_runtime_contract,
)


AGENTS = [
    {"id": "teacher-1", "name": "Teacher", "role": "professor"},
    {"id": "student-1", "name": "Student", "role": "student"},
]


def test_runtime_contract_accepts_playable_v2_slide_scene():
    report = validate_classroom_runtime_contract(
        [
            {
                "id": "scene-1",
                "type": "slide",
                "title": "Water evidence",
                "content": {
                    "type": "slide",
                    "canvas": {
                        "id": "slide-1",
                        "canvasWidth": 1000,
                        "canvasHeight": 562.5,
                        "elements": [
                            {
                                "id": "title_1",
                                "type": "text",
                                "x": 60,
                                "y": 40,
                                "width": 880,
                                "height": 70,
                                "content": "Water evidence lab",
                            },
                            {
                                "id": "image_1",
                                "type": "image",
                                "x": 560,
                                "y": 150,
                                "width": 360,
                                "height": 250,
                                "src": "/media/tenant/1/maic/water.jpg",
                                "content": "Students testing water samples",
                            },
                        ],
                    },
                },
                "actions": [
                    {
                        "id": "speech-1",
                        "type": "speech",
                        "agentId": "teacher-1",
                        "text": "Use the sample evidence before making a claim.",
                    },
                    {
                        "id": "laser-1",
                        "type": "laser",
                        "elementId": "image_1",
                    },
                    {
                        "id": "discussion-1",
                        "type": "discussion",
                        "topic": "Which sample needs action?",
                        "agentId": "teacher-1",
                        "agentIds": ["teacher-1", "student-1"],
                        "sessionType": "roundtable",
                        "triggerMode": "manual",
                    },
                ],
            }
        ],
        AGENTS,
    )

    assert report.is_valid
    assert report.to_dict()["errorCount"] == 0


def test_runtime_contract_rejects_broken_slide_and_handoff_targets():
    report = validate_classroom_runtime_contract(
        [
            {
                "id": "scene-bad",
                "type": "slide",
                "content": {
                    "type": "slide",
                    "canvas": {
                        "id": "slide-bad",
                        "canvasWidth": 1000,
                        "canvasHeight": 562.5,
                        "elements": [
                            {
                                "id": "leak",
                                "type": "text",
                                "x": 60,
                                "y": 40,
                                "width": 900,
                                "height": 80,
                                "content": "Output pure JSON. Aspect ratio 16:9.",
                            },
                            {
                                "id": "off-canvas",
                                "type": "image",
                                "x": 900,
                                "y": 500,
                                "width": 300,
                                "height": 200,
                                "src": "https://placehold.co/800x450",
                            },
                        ],
                    },
                },
                "actions": [
                    {
                        "id": "speech-1",
                        "type": "speech",
                        "agentId": "ghost",
                        "text": "This should not persist.",
                    },
                    {
                        "id": "spotlight-1",
                        "type": "spotlight",
                        "elementId": "missing",
                    },
                    {
                        "id": "discussion-1",
                        "type": "discussion",
                        "topic": "Bad handoff",
                        "agentIds": ["ghost"],
                        "sessionType": "debate",
                        "triggerMode": "instant",
                    },
                    {
                        "id": "speech-after-discussion",
                        "type": "speech",
                        "agentId": "teacher-1",
                        "text": "Discussion should have been last.",
                    },
                ],
            }
        ],
        AGENTS,
    )

    codes = {issue.code for issue in report.errors}
    assert {
        "element.prompt_leak",
        "element.bounds.canvas",
        "image.src.placeholder",
        "agent.unknown",
        "action.target",
        "discussion.order",
        "discussion.session",
        "discussion.trigger",
    }.issubset(codes)


def test_runtime_contract_require_raises_with_actionable_summary():
    with pytest.raises(ValueError, match=r"slide.elements.empty"):
        require_valid_classroom_runtime_contract(
            [
                {
                    "id": "empty-slide-scene",
                    "type": "slide",
                    "content": {
                        "type": "slide",
                        "canvas": {
                            "id": "empty-slide",
                            "canvasWidth": 1000,
                            "canvasHeight": 562.5,
                            "elements": [],
                        },
                    },
                    "actions": [],
                }
            ],
            AGENTS,
        )
