"""
SkinSense — Education / Conditions Endpoint v2.0
Serves HAM10000 class condition profiles for the Education section.
Endpoint: GET /api/conditions
          GET /api/conditions/<class_id>
"""
import json
import os
from flask import Blueprint, jsonify, current_app, request, session

conditions_bp = Blueprint('conditions', __name__)

# ── Complete HAM10000 class education data ──
CONDITION_LIBRARY = [
    {
        "class_id": "nv",
        "name": "Melanocytic Nevi (Common Mole)",
        "category": "Benign",
        "risk_level": "Low",
        "prevalence": "Very common",
        "description": "Melanocytic nevi are common benign proliferations of melanocytes (pigment-producing cells). They appear as brown or black spots and are generally harmless. Most people have 10–40 moles by adulthood.",
        "symptoms": ["Round or oval shape", "Uniform brown/black color", "Smooth, well-defined borders", "Usually < 6mm diameter", "Stable appearance over years"],
        "common_locations": ["Face", "Trunk", "Arms", "Legs"],
        "treatment_options": [
            "No treatment required for typical moles",
            "Surgical excision if showing ABCDE changes",
            "Regular monitoring with dermoscopy",
            "Photographic documentation for comparison"
        ],
        "recommendation": "Perform monthly self-skin checks using the ABCDE rule. See a dermatologist annually if you have more than 50 moles, a family history of melanoma, or atypical-looking moles.",
        "abcde_flags": {"A": "Low", "B": "Low", "C": "Low", "D": "Low", "E": "Low"}
    },
    {
        "class_id": "mel",
        "name": "Melanoma",
        "category": "Malignant",
        "risk_level": "High",
        "prevalence": "~1 in 38 Americans will develop melanoma in their lifetime",
        "description": "Melanoma is the most dangerous form of skin cancer, arising from melanin-producing melanocytes. It can metastasize rapidly to lymph nodes and distant organs. Early detection is critical for survival — 5-year survival rate is ~99% for localized disease but drops to ~30% for distant metastasis.",
        "symptoms": ["Asymmetric shape", "Irregular, notched, or scalloped borders", "Multiple or unusual colors (black, brown, red, pink, white)", "Diameter > 6mm", "Evolving size, shape, or color", "Itching or bleeding"],
        "common_locations": ["Back (men)", "Legs (women)", "Face", "Neck", "Scalp"],
        "treatment_options": [
            "Wide local excision (primary treatment)",
            "Sentinel lymph node biopsy",
            "Immunotherapy (checkpoint inhibitors: pembrolizumab, nivolumab)",
            "Targeted therapy (BRAF/MEK inhibitors for BRAF-mutated melanoma)",
            "Radiation therapy for metastatic disease",
            "Clinical trial enrollment"
        ],
        "recommendation": "URGENT: If you see any ABCDE warning signs, see a board-certified dermatologist or melanoma specialist immediately. Do not delay — melanoma detected at stage 1 has a 95%+ cure rate.",
        "abcde_flags": {"A": "High", "B": "High", "C": "High", "D": "High", "E": "High"}
    },
    {
        "class_id": "bcc",
        "name": "Basal Cell Carcinoma",
        "category": "Malignant",
        "risk_level": "High",
        "prevalence": "Most common skin cancer (3.6 million cases/year in US)",
        "description": "Basal cell carcinoma (BCC) is the most common cancer in humans, arising from basal cells in the deepest layer of the epidermis. While rarely fatal, it can cause significant local tissue destruction if untreated. BCC almost never metastasizes but recurs locally if incompletely removed.",
        "symptoms": ["Pearly or waxy bump (often with visible blood vessels)", "Flat flesh-colored or brown scar-like lesion", "Bleeding, scabbing sore that heals and returns", "Pink growth with raised edges and central indentation", "Scar-like lesion without prior injury"],
        "common_locations": ["Head and neck (80%)", "Trunk", "Sun-exposed areas"],
        "treatment_options": [
            "Mohs micrographic surgery (highest cure rate, 99%)",
            "Excisional surgery",
            "Electrodessication and curettage",
            "Cryotherapy (for superficial lesions)",
            "Topical imiquimod or 5-fluorouracil",
            "Vismodegib (Hedgehog pathway inhibitor) for advanced disease"
        ],
        "recommendation": "BCC is highly treatable when caught early. Avoid sun exposure, use SPF 30+ broad-spectrum sunscreen daily, and have annual skin examinations.",
        "abcde_flags": {"A": "Medium", "B": "Medium", "C": "Low", "D": "Medium", "E": "Medium"}
    },
    {
        "class_id": "akiec",
        "name": "Actinic Keratosis / Intraepithelial Carcinoma",
        "category": "Pre-cancerous",
        "risk_level": "Moderate",
        "prevalence": "Affects ~58 million Americans",
        "description": "Actinic keratoses (AK) are pre-cancerous lesions caused by cumulative UV damage. Approximately 5–10% of untreated AKs progress to squamous cell carcinoma (SCC) within 10 years. Intraepithelial carcinoma (Bowen's disease) is SCC in situ — confined to the epidermis.",
        "symptoms": ["Rough, dry, scaly patch (1–2.5 cm)", "Flat to slightly raised patch on sun-damaged skin", "Hard, wart-like surface in some cases", "Itching, burning, or tenderness", "Color: pink, red, or brownish"],
        "common_locations": ["Face", "Ears", "Scalp", "Neck", "Back of hands", "Forearms", "Lips"],
        "treatment_options": [
            "Cryotherapy (liquid nitrogen) — most common",
            "Topical 5-fluorouracil (Efudex) cream",
            "Topical imiquimod (Aldara)",
            "Photodynamic therapy (PDT)",
            "Diclofenac sodium gel",
            "Curettage and cryosurgery for thick lesions"
        ],
        "recommendation": "Do not ignore rough or scaly patches. AKs are treatable and prevention of SCC is the goal. Lifetime sun protection is essential. Report any new rough patches to a dermatologist.",
        "abcde_flags": {"A": "Low", "B": "Medium", "C": "Low", "D": "Medium", "E": "Medium"}
    },
    {
        "class_id": "bkl",
        "name": "Benign Keratosis-like Lesions",
        "category": "Benign",
        "risk_level": "Low",
        "prevalence": "Very common; seborrheic keratoses appear in virtually all adults by age 50",
        "description": "This category includes solar lentigines (age/sun spots), seborrheic keratoses (stuck-on waxy plaques), and lichen-planus-like keratoses. All are benign and do not progress to cancer, though they can be cosmetically concerning.",
        "symptoms": ["Seborrheic keratosis: waxy, stuck-on appearance, warty texture", "Solar lentigo: flat brown spots on sun-exposed skin", "Color: tan, brown, yellow, or black", "Sharply demarcated borders", "Often multiple lesions appearing with age"],
        "common_locations": ["Face", "Scalp", "Chest", "Back", "Shoulders", "Dorsal hands"],
        "treatment_options": [
            "No treatment required (benign)",
            "Cryotherapy for cosmetic removal",
            "Curettage or shave excision",
            "Laser therapy (Er:YAG, CO2)",
            "Hydrogen peroxide 40% solution (Eskata) for seborrheic keratoses"
        ],
        "recommendation": "These lesions are benign, but any lesion that changes rapidly, bleeds unexpectedly, or develops an irregular border should be evaluated to rule out melanoma or BCC.",
        "abcde_flags": {"A": "Low", "B": "Low", "C": "Low", "D": "Low", "E": "Low"}
    },
    {
        "class_id": "df",
        "name": "Dermatofibroma",
        "category": "Benign",
        "risk_level": "Low",
        "prevalence": "Common; more frequent in women",
        "description": "Dermatofibromas are common benign fibrous nodules of the dermis composed of proliferated fibroblasts. They are firm to the touch and typically asymptomatic. The characteristic 'dimple sign' (lesion depresses inward when pinched) helps distinguish them from melanoma.",
        "symptoms": ["Firm, dome-shaped nodule", "Brown, tan, or pinkish color", "Dimple sign (pinching causes central depression)", "Mild itching or tenderness", "Typically 0.5–1.5 cm"],
        "common_locations": ["Lower legs (most common)", "Arms", "Upper trunk"],
        "treatment_options": [
            "No treatment required (benign)",
            "Surgical excision if symptomatic or cosmetically bothersome",
            "Cryotherapy for superficial lesions",
            "Intralesional corticosteroids for tender lesions"
        ],
        "recommendation": "Dermatofibromas are harmless and do not require treatment. However, any rapidly growing, ulcerating, or atypically appearing lesion should be biopsied to exclude rare dermatofibrosarcoma protuberans.",
        "abcde_flags": {"A": "Low", "B": "Low", "C": "Low", "D": "Low", "E": "Low"}
    },
    {
        "class_id": "vasc",
        "name": "Vascular Lesions",
        "category": "Vascular",
        "risk_level": "Moderate",
        "prevalence": "Common; cherry angiomas affect ~75% of adults over 30",
        "description": "This heterogeneous group includes cherry angiomas (senile angiomas), angiokeratomas, pyogenic granulomas, and hemorrhagic lesions. Most are benign vascular proliferations. Pyogenic granulomas can bleed profusely and may need treatment.",
        "symptoms": ["Cherry angioma: bright red, dome-shaped papule", "Angiokeratoma: dark red/blue-black keratotic papule", "Pyogenic granuloma: rapidly growing red papule, bleeds easily", "Purpura/hemorrhage: flat purple-red discoloration"],
        "common_locations": ["Trunk (cherry angiomas)", "Scrotum/vulva (angiokeratomas)", "Lips, gingiva, fingers (pyogenic granuloma)", "Legs (purpura)"],
        "treatment_options": [
            "Cherry angioma: pulsed dye laser, electrocautery, cryotherapy",
            "Pyogenic granuloma: shave excision, curettage, silver nitrate",
            "Angiokeratoma: laser ablation, cryotherapy",
            "Hemorrhage: pressure, hematology evaluation if systemic"
        ],
        "recommendation": "Most vascular lesions are benign, but a rapidly growing vascular lesion that bleeds easily (especially in pregnancy) should be evaluated promptly to rule out pyogenic granuloma or rare angiosarcoma.",
        "abcde_flags": {"A": "Low", "B": "Low", "C": "Medium", "D": "Low", "E": "Medium"}
    },
    {
        "class_id": "scc",
        "name": "Squamous Cell Carcinoma",
        "category": "Malignant",
        "risk_level": "High",
        "prevalence": "Second most common skin cancer (~1 million US cases/year)",
        "description": "Squamous cell carcinoma (SCC) arises from squamous cells in the outer skin layers. It can metastasize in 2–5% of cases, particularly in immunocompromised patients. Often arises from actinic keratoses on chronically sun-damaged skin.",
        "symptoms": ["Firm, red nodule", "Flat lesion with a scaly, crusted surface", "New sore or raised area on an old scar", "Rough, scaly patch on the lip", "Wart-like growth", "Open sore or ulceration"],
        "common_locations": ["Face", "Ears", "Neck", "Hands", "Forearms", "Lips (high-risk)"],
        "treatment_options": [
            "Mohs micrographic surgery (gold standard for high-risk lesions)",
            "Excisional surgery",
            "Radiation therapy",
            "Cemiplimab (Libtayo) for locally advanced or metastatic disease",
            "Topical treatments for superficial lesions"
        ],
        "recommendation": "SCC requires prompt medical evaluation and treatment. Patients with SCC should have 3–6 monthly follow-ups for the first 2 years. High-risk patients should also be examined for regional lymph node involvement.",
        "abcde_flags": {"A": "Medium", "B": "Medium", "C": "Medium", "D": "Medium", "E": "High"}
    },
    {
        "class_id": "psoriasis",
        "name": "Psoriasis",
        "category": "Inflammatory",
        "risk_level": "Moderate",
        "prevalence": "Affects 2–3% of the global population",
        "description": "Psoriasis is a chronic autoimmune condition causing rapid skin cell buildup, resulting in scaling and inflammation. It is not contagious. Beyond skin manifestations, psoriasis is associated with psoriatic arthritis, cardiovascular disease, and metabolic syndrome.",
        "symptoms": ["Red patches covered with thick, silvery scales", "Dry, cracked skin that may bleed", "Itching, burning, or soreness", "Thickened, pitted, or ridged nails", "Stiff, swollen joints (psoriatic arthritis)"],
        "common_locations": ["Scalp", "Elbows", "Knees", "Lower back", "Palms", "Soles"],
        "treatment_options": [
            "Topical corticosteroids (first-line)",
            "Topical vitamin D analogues (calcipotriol)",
            "Phototherapy (UVB, PUVA)",
            "Methotrexate, cyclosporine, acitretin (systemic)",
            "Biologics: TNF-α inhibitors, IL-17/IL-23 inhibitors",
            "JAK inhibitors (deucravacitinib)"
        ],
        "recommendation": "Psoriasis is a chronic condition requiring long-term management. Work with a dermatologist to find a treatment regimen that controls symptoms. Identify and avoid personal triggers (stress, alcohol, smoking, certain medications).",
        "abcde_flags": {"A": "Low", "B": "Low", "C": "Low", "D": "Medium", "E": "Medium"}
    }
]

# Build lookup map for fast retrieval
_CONDITION_MAP = {c['class_id']: c for c in CONDITION_LIBRARY}


@conditions_bp.route('/api/conditions', methods=['GET'])
def list_conditions():
    """
    GET /api/conditions
    Public endpoint — returns the education condition library.
    Supports: ?search=, ?category=, ?risk=, ?lang=
    """
    search   = (request.args.get('search', '') or '').lower()
    category = (request.args.get('category', '') or '').lower()
    risk     = (request.args.get('risk', '') or '').lower()
    lang     = (request.args.get('lang', '') or 'en').lower()

    db_path  = current_app.config.get('DATABASE_PATH')
    kb_items = {}
    if db_path:
        from backend.services.personalized_care_service import PersonalizedCareService
        care_svc = PersonalizedCareService(db_path)
        for c in CONDITION_LIBRARY:
            guidance = care_svc.get_guidance_for_condition(c['class_id'], lang=lang)
            if guidance and guidance.get('is_approved_kb'):
                kb_items[c['class_id']] = guidance

    results = []
    for c in CONDITION_LIBRARY:
        cid = c['class_id']
        kb = kb_items.get(cid, {})
        name = kb.get('condition_name') or c['name']
        desc = kb.get('description') or c['description']
        cat  = kb.get('category') or c['category']
        r_level = kb.get('risk_level') or c['risk_level']

        item = {
            'class_id':    cid,
            'name':        name,
            'category':    cat,
            'risk_level':  r_level,
            'prevalence':  c.get('prevalence', ''),
            'description': desc[:200] + '…' if len(desc) > 200 else desc,
        }
        results.append(item)

    if search:
        results = [c for c in results
                   if search in c['name'].lower()
                   or search in c['description'].lower()
                   or search in c['category'].lower()]
    if category and category != 'all':
        results = [c for c in results if c['category'].lower() == category]
    if risk and risk != 'all':
        results = [c for c in results if c['risk_level'].lower() == risk]

    return jsonify({'status': 'success', 'count': len(results), 'conditions': results})


@conditions_bp.route('/api/conditions/<class_id>', methods=['GET'])
def get_condition(class_id):
    """
    GET /api/conditions/<class_id>
    Returns full condition detail for education section.
    Attempts DB knowledge base first, falls back to in-memory library.
    """
    db_path = current_app.config.get('DATABASE_PATH')
    lang = request.args.get('lang', 'en').lower()

    if db_path:
        from backend.services.personalized_care_service import PersonalizedCareService
        care_svc = PersonalizedCareService(db_path)
        kb_item = care_svc.get_guidance_for_condition(class_id, lang=lang)
        if kb_item and kb_item.get('is_approved_kb'):
            return jsonify({'status': 'success', 'condition': kb_item})

    condition = _CONDITION_MAP.get(class_id.lower())
    if not condition:
        return jsonify({'status': 'error', 'message': f'Condition "{class_id}" not found.'}), 404

    return jsonify({'status': 'success', 'condition': condition})


@conditions_bp.route('/api/conditions/knowledge/<class_id>', methods=['GET'])
def get_condition_knowledge(class_id):
    """
    GET /api/conditions/knowledge/<class_id>?lang=en|hi|mr
    Returns structured home-care knowledge base item for a specific condition.
    """
    db_path = current_app.config.get('DATABASE_PATH')
    lang = request.args.get('lang', 'en').lower()

    if not db_path:
        return jsonify({'status': 'error', 'message': 'Database not configured.'}), 500

    from backend.services.personalized_care_service import PersonalizedCareService
    care_svc = PersonalizedCareService(db_path)
    guidance = care_svc.get_guidance_for_condition(class_id, lang=lang)

    return jsonify({'status': 'success', 'guidance': guidance})


@conditions_bp.route('/api/conditions/personalized-guidance', methods=['POST'])
def get_personalized_guidance_route():
    """
    POST /api/conditions/personalized-guidance
    Body JSON: {
        "condition_code": "nv",
        "itching": 5, "pain": 2, "duration_days": 10, "body_region": "arm",
        "is_spreading": false, "has_discharge": false, "is_cracked_bleeding": true,
        "new_cosmetic_product": false, "lang": "en"
    }
    Returns custom personalized home-care guidance based on patient answers.
    """
    data = request.get_json() or {}
    condition_code = data.get('condition_code', 'unknown')
    lang = (data.get('lang') or 'en').lower()
    db_path = current_app.config.get('DATABASE_PATH')

    if not db_path:
        return jsonify({'status': 'error', 'message': 'Database not configured.'}), 500

    from backend.services.personalized_care_service import PersonalizedCareService
    conversation = current_app.config.get('CONVERSATION_SERVICE')
    client = conversation.client if conversation and session.get('user_id') else None
    care_svc = PersonalizedCareService(db_path, gemini_client=client)
    guidance = care_svc.get_guidance_for_condition(
        condition_code,
        symptom_data=data,
        lang=lang,
        is_reliable=data.get('is_reliable') is not False,
        assessment_status=data.get('assessment_status', 'assessed'),
        use_gemini=True,
    )

    return jsonify({'status': 'success', 'guidance': guidance})


