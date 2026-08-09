import json
from pathlib import Path

import pytest

from schemas.artifacts import validate_artifact

ROOT = Path(__file__).resolve().parents[2]


def _proposal():
    from tests.contracts.test_phase0_contracts import sample_artifact
    value = sample_artifact('proposal_packet')
    value['production_plan']['video_category'] = 'overview-video'
    value['production_plan']['taste_profile'].update({
        'focal_strategy': 'One dominant evidence subject per beat.',
        'surface_system': 'One coherent radius, edge, elevation and glow system.',
        'motion_grammar': 'Semantic primary action, supporting camera, restrained ambience, readable settle.',
        'transition_strategy': 'Focus handoff through shared geometry or deliberate cuts.',
        'keyframe_quality_floor': 'premium-keyvisual',
        'restraint_rules': ['No generic dashboard showcase'],
        'hero_moments': ['evidence handoff', 'final synthesis'],
    })
    value['production_plan']['semantic_visual_review'] = {
        'required': True,
        'models': ['zai/glm-4.5v'],
        'max_iterations': 3,
        'hook_window_seconds': 3,
        'minimum_frames': 12,
        'human_approval_required': True,
    }
    return value


def test_overview_proposal_requires_rendered_semantic_review_contract():
    value = _proposal()
    validate_artifact('proposal_packet', value)
    del value['production_plan']['semantic_visual_review']
    with pytest.raises(Exception):
        validate_artifact('proposal_packet', value)


def test_overview_edit_requires_semantic_review_contract():
    value = {
        'version': '1.0',
        'renderer_family': 'bespoke',
        'render_runtime': 'remotion',
        'composition_mode': 'atelier',
        'video_category': 'overview-video',
        'bespoke': {
            'entry': 'remotion/index.tsx', 'composition_id': 'Hero',
            'art_direction': 'Real UI editorial film.',
            'scene_inventory': [{'scene_id':'s1','primary_subject':'evidence','signature_device_present':True}],
        },
        'subtitles': {
            'enabled': True, 'style':'phrase', 'language_code':'de-DE',
            'unicode_normalization':'NFC', 'layout_policy':'reserved-rail',
            'preferred_zone':'bottom', 'safe_margin_px':48,
            'reserved_rail_height_px':208, 'protected_regions':[],
            'visual_treatment':'integrated-field', 'full_width_background':False,
        },
        'semantic_visual_review': {
            'required': True, 'models':['zai/glm-4.5v'], 'max_iterations':3,
            'hook_window_seconds':3, 'minimum_frames':12,
            'human_approval_required':True,
        },
    }
    validate_artifact('edit_decisions', value)
    del value['semantic_visual_review']
    with pytest.raises(Exception):
        validate_artifact('edit_decisions', value)


def test_script_supports_three_hook_candidates_and_playable_direction():
    value = {
        'version':'1.0','title':'Hook test','total_duration_seconds':10,
        'hook_contract':{
            'hook_type':'evidence_gap','window_seconds':3,
            'selected_candidate_id':'h1','first_visual_proof_seconds':0.4,
            'candidates':[
                {'id':'h1','spoken_text':'Wo ist der Beleg?','visual_proof':'Source close-up','why_it_earns_attention':'Immediate evidence gap'},
                {'id':'h2','spoken_text':'Eine Antwort ohne Quelle ist nur Behauptung.','visual_proof':'Unlinked answer','why_it_earns_attention':'Consequence'},
                {'id':'h3','spoken_text':'Diese Antwort kann sich selbst beweisen.','visual_proof':'Linked citation','why_it_earns_attention':'Surprising proof'},
            ],
        },
        'sections':[{
            'id':'s1','text':'Wo ist der Beleg?','start_seconds':0,'end_seconds':3,
            'delivery_cues':{
                'pace':'measured','intent':'Challenge the viewer','stance':'investigative',
                'operative_words':['Beleg'],'pause_plan':'Pause after question',
                'energy_curve':'direct to controlled','visual_landing':'Source appears on Beleg',
            }
        }]
    }
    validate_artifact('script', value)


def test_binding_docs_define_visual_learning_and_caption_limits():
    text=(ROOT/'docs'/'EDITORIAL_PERFORMANCE_AND_RETENTION.md').read_text()
    for phrase in ['0–3 second window', '42 characters per line', '17 characters per second',
                   'maximum three-iteration loop', 'human listening decision',
                   'no nested translucent rounded-rectangle outlines']:
        assert phrase in text
