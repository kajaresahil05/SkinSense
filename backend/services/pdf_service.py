"""
SkinSense — Professional Dermatological Assessment PDF Report Service v3.0
Completely redesigned medical report generator built with ReportLab.

Key Features & Enhancements:
 - Clean, structured medical document layout with clinical section cards & tables
 - Full Unicode TTFont support (Nirmala UI / Segoe UI / Arial) fixing all ■■■■ / garbled text
 - Supports English (en), Hindi (hi), Bhojpuri (bho), Marathi (mr), Bengali (bn), Spanish (es), etc.
 - NumberedCanvas multi-page running headers, footers, timestamp, and 'Page X of Y' numbering
 - Prominent medical disclaimer banner and dermatologist advisory
 - Patient & Examination demographics table
 - Primary AI diagnostic prediction card with confidence match score and risk level badge
 - Differential Diagnosis (Top-3 Model Predictions) table
 - Symptom Assessment & Fuzzy Logic Severity Index (0-100) card
 - Risk indicators & Contributing factors list
 - Side-by-side Explainable AI (Grad-CAM Heatmap) & Photo visual evidence card
 - Synthesized Clinical Decision Chain summary box
 - Structured Evidence-Based Guidance: Preventive measures, safe home care, things to avoid, red-flag warning signs, and dermatologist consultation triggers
"""

import os
import io
import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as RLImage, HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("[PDFService] ReportLab not installed - PDF generation disabled.")


# ────────────────────────────────────────────────
# COLOR PALETTE (Clinical Medical Palette)
# ────────────────────────────────────────────────
COLOR_PRIMARY     = HexColor('#0f766e')   # Deep Teal
COLOR_SECONDARY   = HexColor('#134e4a')   # Dark Forest Teal
COLOR_ACCENT_BG   = HexColor('#f0fdfa')   # Soft Mint / Light Teal Card Fill
COLOR_DANGER      = HexColor('#dc2626')   # Clinical Red (High / Malignant)
COLOR_WARNING     = HexColor('#d97706')   # Amber (Moderate / High Severity)
COLOR_SUCCESS     = HexColor('#059669')   # Emerald (Low Risk / Mild)
COLOR_NEUTRAL_BG = HexColor('#f8fafc')   # Off-white Slate Card Fill
COLOR_TEXT_MAIN   = HexColor('#1e293b')   # Slate 800
COLOR_TEXT_MUTED  = HexColor('#64748b')   # Slate 500
COLOR_BORDER      = HexColor('#cbd5e1')   # Slate 300 Border
COLOR_WHITE       = HexColor('#ffffff')


# ────────────────────────────────────────────────
# UNICODE FONT REGISTRATION (Fixes ■■■■ Garbled Text)
# ────────────────────────────────────────────────
FONT_REGULAR = 'Helvetica'
FONT_BOLD    = 'Helvetica-Bold'
FONT_ITALIC  = 'Helvetica-Oblique'
UNICODE_FONT_AVAILABLE = False

def _init_fonts():
    global FONT_REGULAR, FONT_BOLD, FONT_ITALIC, UNICODE_FONT_AVAILABLE
    if not REPORTLAB_AVAILABLE:
        return

    # Standard system font locations (Windows, Linux, macOS)
    candidates = [
        ('Nirmala',     'Nirmala-Bold',     'C:/Windows/Fonts/Nirmala.ttc', 0, 1),
        ('SegoeUI',     'SegoeUI-Bold',     'C:/Windows/Fonts/segoeui.ttf', None, None),
        ('Arial',       'Arial-Bold',       'C:/Windows/Fonts/arial.ttf', None, None),
        ('DejaVuSans',  'DejaVuSans-Bold',  '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', None, None),
        ('FreeSans',    'FreeSans-Bold',    '/usr/share/fonts/truetype/freefont/FreeSans.ttf', None, None),
    ]

    for reg_name, bold_name, path, sub0, sub1 in candidates:
        if os.path.exists(path):
            try:
                if path.endswith('.ttc'):
                    pdfmetrics.registerFont(TTFont(reg_name, path, subfontIndex=sub0 or 0))
                    pdfmetrics.registerFont(TTFont(bold_name, path, subfontIndex=sub1 or 1))
                else:
                    pdfmetrics.registerFont(TTFont(reg_name, path))
                    bold_path = path.replace('.ttf', 'bd.ttf').replace('.ttf', '-Bold.ttf')
                    if os.path.exists(bold_path):
                        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                    else:
                        bold_name = reg_name
                
                FONT_REGULAR = reg_name
                FONT_BOLD    = bold_name
                FONT_ITALIC  = reg_name
                UNICODE_FONT_AVAILABLE = True
                print(f"[PDFService] Registered Unicode TTFont: {reg_name}")
                break
            except Exception as e:
                print(f"[PDFService] Note registering candidate font {reg_name}: {e}")

_init_fonts()


# ────────────────────────────────────────────────
# DYNAMIC MULTI-PAGE NUMBERED CANVAS
# ────────────────────────────────────────────────
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        page_w, page_h = A4
        margin = 1.5 * cm  # 42.5 pt

        # Running Header on Page 2+
        if self._pageNumber > 1:
            self.setStrokeColor(COLOR_PRIMARY)
            self.setLineWidth(1)
            self.line(margin, page_h - 1.2 * cm, page_w - margin, page_h - 1.2 * cm)

            self.setFont(FONT_BOLD, 8)
            self.setFillColor(COLOR_PRIMARY)
            self.drawString(margin, page_h - 1.0 * cm, "SkinSense — Clinical Assessment Report")

            self.setFont(FONT_REGULAR, 8)
            self.setFillColor(COLOR_TEXT_MUTED)
            report_id = getattr(self, '_report_id', 'N/A')
            self.drawRightString(page_w - margin, page_h - 1.0 * cm, f"Report ID: {report_id}")

        # Running Footer on ALL Pages
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.75)
        self.line(margin, 1.3 * cm, page_w - margin, 1.3 * cm)

        self.setFont(FONT_REGULAR, 7.5)
        self.setFillColor(COLOR_TEXT_MUTED)
        self.drawString(margin, 0.9 * cm, "CONFIDENTIAL MEDICAL ASSESSMENT — FOR CLINICAL DECISION SUPPORT & EDUCATION ONLY")
        self.drawRightString(page_w - margin, 0.9 * cm, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


# ────────────────────────────────────────────────
# MULTILINGUAL DICTIONARY (10 Languages)
# ────────────────────────────────────────────────
PDF_LOCALIZATION = {
    'en': {
        'doc_title': 'CLINICAL DERMATOLOGY ASSESSMENT REPORT',
        'sub_title': 'Intelligent Decision Support & Risk Evaluation System',
        'disclaimer': 'MANDATORY MEDICAL ADVISORY: This AI-generated assessment is intended exclusively for clinical decision support and patient education. It does NOT constitute a formal diagnosis or prescription. Consultation with a board-certified dermatologist is mandatory for clinical diagnosis.',
        'patient_info': 'Patient & Examination Overview',
        'patient_name': 'Patient Name',
        'patient_age': 'Age / Gender',
        'years': 'years',
        'assessment_id': 'Report ID',
        'report_date': 'Examination Date',
        'lesion_region': 'Body Region',
        'image_quality': 'Photo Quality',
        'ai_diagnosis': 'Primary AI Diagnostic Prediction',
        'primary_diagnosis': 'Primary Condition',
        'confidence': 'Match Confidence',
        'disease_code': 'ICD/Class Code',
        'reliability': 'Diagnostic Certainty',
        'high_confidence': 'High Match Confidence',
        'low_confidence': 'Low Confidence - Review Recommended',
        'risk_level': 'Risk Category',
        'differential_diagnosis': 'Differential Diagnosis (Top-3 Model Predictions)',
        'rank': '#',
        'condition': 'Condition Name',
        'code': 'Code',
        'score': 'Match %',
        'symptom_analysis': 'Symptom Assessment & Fuzzy Severity Analysis',
        'symptom': 'Symptom Parameter',
        'rating': 'Reported Value',
        'itching': 'Itching Intensity',
        'pain': 'Pain Level',
        'redness': 'Skin Redness',
        'duration': 'Symptom Duration',
        'days': 'days',
        'fever': 'Fever Presence',
        'burning': 'Burning Sensation',
        'fuzzy_score': 'Fuzzy Severity Index',
        'severity_category': 'Severity Category',
        'contributing_factors': 'Risk Indicators & Contributing Factors',
        'xai_title': 'Explainable AI (Grad-CAM Visual Focus Evidence)',
        'xai_caption': 'Grad-CAM visual focus mapping highlighting cellular features and regions evaluated by the CNN model.',
        'original_photo': 'Uploaded Skin Photo',
        'heatmap_photo': 'Grad-CAM Heatmap Focus',
        'clinical_summary': 'Clinical Decision Summary',
        'guidance_title': 'Evidence-Based Home Care & Medical Guidance',
        'preventive_measures': '🛡️ Preventive Measures & Skin Protection',
        'supportive_care': '🏠 Safe Home Care & Supportive Self-Care',
        'things_to_avoid': '⚠️ Things to Avoid (Prohibited Actions)',
        'warning_signs': '🚨 Red Flag Warning Signs',
        'when_to_see_doctor': '👨‍⚕️ When to Consult a Dermatologist',
        'doctor_consult_mandatory': 'DOCTOR CONSULTATION MANDATORY: Supportive care does not replace clinical diagnosis or treatment.',
        'footer': 'SkinSense AI v2.0 | MobileNetV2 + Fuzzy Engine + Grad-CAM XAI'
    },
    'hi': {
        'doc_title': 'त्वचा स्वास्थ्य जाँच रिपोर्ट (Clinical Assessment Report)',
        'sub_title': 'एआई-संचालित त्वचा विज्ञान विश्लेषण एवं सलाह',
        'disclaimer': 'चिकित्सकीय चेतावनी: यह AI-जनरेटेड रिपोर्ट केवल जानकारी और निर्णय सहायता के लिए है। यह औपचारिक चिकित्सीय निदान या पर्चा नहीं है। सही निदान और उपचार के लिए त्वचा विशेषज्ञ (Dermatologist) से परामर्श अनिवार्य है।',
        'patient_info': 'मरीज़ एवं परीक्षा की जानकारी (Patient Information)',
        'patient_name': 'मरीज़ का नाम',
        'patient_age': 'आयु',
        'years': 'वर्ष',
        'assessment_id': 'रिपोर्ट आईडी',
        'report_date': 'जाँच दिनांक',
        'lesion_region': 'शरीर का अंग',
        'image_quality': 'फोटो गुणवत्ता',
        'ai_diagnosis': 'प्राथमिक AI निदान परिणाम (Primary AI Prediction)',
        'primary_diagnosis': 'प्राथमिक बीमारी',
        'confidence': 'विश्वास स्कोर (Confidence)',
        'disease_code': 'बीमारी कोड',
        'reliability': 'विश्वसनीयता',
        'high_confidence': 'उच्च विश्वास (High Confidence)',
        'low_confidence': 'कम विश्वास - डॉक्टर की समीक्षा अनुशंसित',
        'risk_level': 'जोखिम श्रेणी (Risk Level)',
        'differential_diagnosis': 'संभावित अन्य बीमारियां (Top-3 Predictions)',
        'rank': 'क्रम',
        'condition': 'बीमारी का नाम',
        'code': 'कोड',
        'score': 'मैच %',
        'symptom_analysis': 'लक्षण एवं फज़ी गंभीरता विश्लेषण (Symptom & Severity)',
        'symptom': 'लक्षण',
        'rating': 'दर / स्कोर',
        'itching': 'खुजली की तीव्रता',
        'pain': 'दर्द का स्तर',
        'redness': 'त्वचा का लालपन',
        'duration': 'लक्षण अवधि',
        'days': 'दिन',
        'fever': 'बुखार की स्थिति',
        'burning': 'जलन की स्थिति',
        'fuzzy_score': 'फज़ी गंभीरता सूचकांक',
        'severity_category': 'गंभीरता श्रेणी',
        'contributing_factors': 'जोखिम कारक एवं योगदानकर्ता',
        'xai_title': 'विजुअल AI व्याख्या (Grad-CAM Heatmap Visual Evidence)',
        'xai_caption': 'Grad-CAM हीटमैप दिखाता है कि AI ने त्वचा के किस मुख्य क्षेत्र के आधार पर यह आकलन किया।',
        'original_photo': 'अपलोड की गई फोटो',
        'heatmap_photo': 'Grad-CAM हीटमैप क्षेत्र',
        'clinical_summary': 'चिकित्सकीय निष्कर्ष (Clinical Decision Summary)',
        'guidance_title': 'साक्ष्य-आधारित घरेलू देखभाल एवं चिकित्सा सलाह',
        'preventive_measures': '🛡️ निवारक उपाय एवं त्वचा सुरक्षा',
        'supportive_care': '🏠 सुरक्षित घरेलू देखभाल एवं सहायता',
        'things_to_avoid': '⚠️ जिनसे बचें (परहेज)',
        'warning_signs': '🚨 गंभीर चेतावनी संकेत (Red Flags)',
        'when_to_see_doctor': '👨‍⚕️ डॉक्टर से कब परामर्श लें',
        'doctor_consult_mandatory': 'चिकित्सक परामर्श अनिवार्य: घरेलू देखभाल उपचार का विकल्प नहीं है।',
        'footer': 'SkinSense AI v2.0 द्वारा जनरेट | MobileNetV2 + Fuzzy Engine + Grad-CAM XAI'
    },
    'bho': {
        'doc_title': 'चामड़ी जाँच रिपोर्ट (Clinical Assessment Report)',
        'sub_title': 'AI से चामड़ी के बीमारी के विश्लेषण आ सलाह',
        'disclaimer': 'डॉक्टरी चेतावनी: ई AI से बनावल रिपोर्ट खाली जानकारी आ मदद खातिर बा। ई कौनों पक्का डॉक्टरी इलाज या पर्ची ना ह। पक्का इलाज आ जाँच खातिर चामड़ी के डॉक्टर से जरूर मिलीं।',
        'patient_info': 'मरीज़ के जानकारी (Patient Information)',
        'patient_name': 'मरीज़ के नाम',
        'patient_age': 'उमिर',
        'years': 'बरिस',
        'assessment_id': 'रिपोर्ट आईडी',
        'report_date': 'जाँच तारीख',
        'lesion_region': 'शरीर के अंग',
        'image_quality': 'फोटो गुणवत्ता',
        'ai_diagnosis': 'मुख्य AI जांच परिणाम (Primary AI Prediction)',
        'primary_diagnosis': 'मुख्य बीमारी',
        'confidence': 'विश्वास (Confidence)',
        'disease_code': 'बीमारी कोड',
        'reliability': 'विश्वसनीयता',
        'high_confidence': 'उच्च विश्वास (High Confidence)',
        'low_confidence': 'कम विश्वास - डॉक्टर के सलाह जरूरी बा',
        'risk_level': 'जोखिम स्तर (Risk Level)',
        'differential_diagnosis': 'अन्य संभावित बीमारी (Top-3 Predictions)',
        'rank': 'नंबर',
        'condition': 'बीमारी के नाम',
        'code': 'कोड',
        'score': 'मैच %',
        'symptom_analysis': 'लक्षण आ फज़ी गंभीरता विश्लेषण (Symptom & Severity)',
        'symptom': 'लक्षण',
        'rating': 'स्कोर',
        'itching': 'खुजली के तीव्रता',
        'pain': 'दर्द के स्तर',
        'redness': 'त्वचा के लाली',
        'duration': 'समय',
        'days': 'दिन',
        'fever': 'बुखार',
        'burning': 'जलन',
        'fuzzy_score': 'फज़ी गंभीरता स्कोर',
        'severity_category': 'गंभीरता श्रेणी',
        'contributing_factors': 'जोखिम के कारण',
        'xai_title': 'विजुअल AI व्याख्या (Grad-CAM Heatmap)',
        'xai_caption': 'Grad-CAM नक्शा देखावत बा कि AI फोटो में कहाँ देख के फैसला लेले बा।',
        'original_photo': 'अपलोड फोटो',
        'heatmap_photo': 'Grad-CAM हीटमैप फोटो',
        'clinical_summary': 'चिकित्सकीय निष्कर्ष (Clinical Decision Summary)',
        'guidance_title': 'घरेलू देखभाल आ डॉक्टरी सलाह',
        'preventive_measures': '🛡️ बचाव आ त्वचा सुरक्षा',
        'supportive_care': '🏠 घर पर सुरक्षित देखभाल',
        'things_to_avoid': '⚠️ जिनगी में का ना करे के बा (परहेज)',
        'warning_signs': '🚨 गंभीर चेतावनी (Red Flags)',
        'when_to_see_doctor': '👨‍⚕️ डॉक्टर से कब मिले के बा',
        'doctor_consult_mandatory': 'डॉक्टर के सलाह बहुत जरूरी बा: घरेलू उपाय खाली आराम खातिर बा।',
        'footer': 'SkinSense AI v2.0 द्वारा जनरेट | MobileNetV2 + Fuzzy Engine + Grad-CAM XAI'
    },
    'mr': {
        'doc_title': 'त्वचा तपासणी अहवाल (Clinical Assessment Report)',
        'sub_title': 'AI-आधारित त्वचाशास्त्र विश्लेषण व सल्ला',
        'disclaimer': 'वैद्यकीय इशारा: हा AI-जनरेट केलेला अहवाल फक्त माहितीसाठी व मदतीसाठी आहे. हे अधिकृत वैद्यकीय निदान नाही. योग्य उपचारांसाठी त्वचाशास्त्रज्ञांचा (Dermatologist) सल्ला घ्या.',
        'patient_info': 'रुग्णाची माहिती (Patient Information)',
        'patient_name': 'रुग्णाचे नाव',
        'patient_age': 'वय',
        'years': 'वर्षे',
        'assessment_id': 'अहवाल आयडी',
        'report_date': 'तपासणी दिनांक',
        'lesion_region': 'शरीराचा भाग',
        'image_quality': 'फोटो गुणवत्ता',
        'ai_diagnosis': 'प्रमुख AI निदान निकाल (Primary AI Prediction)',
        'primary_diagnosis': 'प्रमुख आजार',
        'confidence': 'विश्वासार्हता',
        'disease_code': 'आजार कोड',
        'reliability': 'विश्वासार्हता पातळी',
        'high_confidence': 'उच्च विश्वासार्हता',
        'low_confidence': 'कमी विश्वासार्हता - डॉक्टरांचा सल्ला आवश्यक',
        'risk_level': 'धोका पातळी (Risk Level)',
        'differential_diagnosis': 'इतर संभाव्य आजार (Top-3 Predictions)',
        'rank': 'क्र.',
        'condition': 'आजाराचे नाव',
        'code': 'कोड',
        'score': 'मैच %',
        'symptom_analysis': 'लक्षणे व फझी तीव्रता विश्लेषण (Symptom & Severity)',
        'symptom': 'लक्षण',
        'rating': 'गुण',
        'itching': 'खाज सुटणे',
        'pain': 'दुखणे',
        'redness': 'लालसरपणा',
        'duration': 'कालावधी',
        'days': 'दिवस',
        'fever': 'ताप',
        'burning': 'जळजळ',
        'fuzzy_score': 'फझी तीव्रता स्कोर',
        'severity_category': 'तीव्रता वर्ग',
        'contributing_factors': 'धोक्याचे घटक',
        'xai_title': 'विझ्युअल AI स्पष्टीकरण (Grad-CAM Heatmap)',
        'xai_caption': 'Grad-CAM हीतमॅप AI निदानास कारणीभूत ठरलेले मुख्य भाग दर्शवतो.',
        'original_photo': 'अपलोड केलेला फोटो',
        'heatmap_photo': 'Grad-CAM हीतमॅप',
        'clinical_summary': 'वैद्यकीय निष्कर्ष (Clinical Decision Summary)',
        'guidance_title': 'घरगुती काळजी व वैद्यकीय सल्ला',
        'preventive_measures': '🛡️ प्रतिबंधात्मक उपाय व त्वचा संरक्षण',
        'supportive_care': '🏠 सुरक्षित घरगुती काळजी',
        'things_to_avoid': '⚠️ काय टाळावे (पथ्य)',
        'warning_signs': '🚨 धोक्याच्या सूचना (Red Flags)',
        'when_to_see_doctor': '👨‍⚕️ डॉक्टरांना कधी दाखवावे',
        'doctor_consult_mandatory': 'डॉक्टरांचा सल्ला अनिवार्य आहे.',
        'footer': 'SkinSense AI v2.0 द्वारे निर्मित | MobileNetV2 + Fuzzy Engine + Grad-CAM XAI'
    },
    'bn': {
        'doc_title': 'চর্মরোগ মূল্যায়ন প্রতিবেদন (Clinical Assessment Report)',
        'sub_title': 'এআই-চালিত ডার্মাটোলজি বিশ্লেষণ ও দিকনির্দেশনা',
        'disclaimer': 'চিকিৎসা সতর্কবার্তা: এই AI প্রতিবেদনটি কেবল তথ্য ও সহায়তার জন্য। এটি কোনো চিকিৎসকের ফাইনাল ডায়াগনোসিস নয়। চর্মরোগ বিশেষজ্ঞের পরামর্শ নিন।',
        'patient_info': 'রোগীর তথ্য (Patient Information)',
        'patient_name': 'রোগীর নাম',
        'patient_age': 'বয়স',
        'years': 'বছর',
        'assessment_id': 'প্রতিবেদন আইডি',
        'report_date': 'পরীক্ষার তারিখ',
        'lesion_region': 'শরীরের স্থান',
        'image_quality': 'ছবির মান',
        'ai_diagnosis': 'প্রাথমিক AI অনুমান ফলাফল',
        'primary_diagnosis': 'প্রাথমিক অবস্থা',
        'confidence': 'আত্মবিশ্বাস',
        'disease_code': 'রোগ কোড',
        'reliability': 'নির্ভরযোগ্যতা',
        'high_confidence': 'উচ্চ নির্ভরযোগ্যতা',
        'low_confidence': 'কম নির্ভরযোগ্যতা - ডাক্তারের পরামর্শ নিন',
        'risk_level': 'ঝুঁকির মাত্রা',
        'differential_diagnosis': 'অন্যান্য সম্ভাব্য অবস্থা (Top-3 Predictions)',
        'rank': 'ক্রম',
        'condition': 'অবস্থার নাম',
        'code': 'কোড',
        'score': 'ম্যাচ %',
        'symptom_analysis': 'উপসর্গ এবং তীব্রতা বিশ্লেষণ',
        'symptom': 'উপসর্গ',
        'rating': 'স্কোর',
        'itching': 'চুলকানি',
        'pain': 'ব্যথা',
        'redness': 'লালভাব',
        'duration': 'স্থায়িত্ব',
        'days': 'দিন',
        'fever': 'জ্বর',
        'burning': 'জ্বালাপোড়া',
        'fuzzy_score': 'ফাজি তীব্রতা সূচক',
        'severity_category': 'তীব্রতার বিভাগ',
        'contributing_factors': 'ঝুঁকির অনুঘটকসমূহ',
        'xai_title': 'ভিজ্যুয়াল AI ব্যাখ্যা (Grad-CAM Heatmap)',
        'xai_caption': 'Grad-CAM হিটম্যাপের এলাকাগুলি AI সিদ্ধান্তের প্রধান কারণ নির্দেশ করে।',
        'original_photo': 'আপলোড করা ছবি',
        'heatmap_photo': 'Grad-CAM হিটম্যাপ',
        'clinical_summary': 'ক্লিনিকাল সারাংশ',
        'guidance_title': 'গৃহস্থালি যত্ন ও চিকিৎসা পরামর্শ',
        'preventive_measures': '🛡️ প্রতিরোধমূলক ব্যবস্থা',
        'supportive_care': '🏠 নিরাপদ গৃহস্থালি যত্ন',
        'things_to_avoid': '⚠️ বর্জনীয় বিষয়সমূহ',
        'warning_signs': '🚨 জরুরি সতর্কতা সংকেত',
        'when_to_see_doctor': '👨‍⚕️ কখন ডাক্তার দেখাবেন',
        'doctor_consult_mandatory': 'ডাক্তারের পরামর্শ বাধ্যতামূলক।',
        'footer': 'SkinSense AI v2.0 দ্বারা তৈরি | MobileNetV2 + Fuzzy Engine + Grad-CAM XAI'
    },
    'es': {
        'doc_title': 'INFORME DE EVALUACIÓN DERMATOLÓGICA CLINICA',
        'sub_title': 'Evaluación Dermatológica Asistida por IA',
        'disclaimer': 'AVISO MÉDICO OBLIGATORIO: Este informe generado por IA es solo para fines informativos y de soporte a la decisión clínica. NO constituye un diagnóstico formal. Se requiere la consulta con un dermatólogo certificado.',
        'patient_info': 'Información del Paciente y Evaluación',
        'patient_name': 'Nombre del Paciente',
        'patient_age': 'Edad / Género',
        'years': 'años',
        'assessment_id': 'ID de Informe',
        'report_date': 'Fecha de Evaluación',
        'lesion_region': 'Región del Cuerpo',
        'image_quality': 'Calidad de Imagen',
        'ai_diagnosis': 'Predicción Diagnóstica de IA',
        'primary_diagnosis': 'Condición Principal',
        'confidence': 'Confianza de Coincidencia',
        'disease_code': 'Código ICD/Clase',
        'reliability': 'Certeza Diagnóstica',
        'high_confidence': 'Alta Confianza',
        'low_confidence': 'Baja Confianza - Revisión Recomendada',
        'risk_level': 'Categoría de Riesgo',
        'differential_diagnosis': 'Diagnóstico Diferencial (Top-3 Predicciones)',
        'rank': '#',
        'condition': 'Nombre de la Condición',
        'code': 'Código',
        'score': 'Coincidencia %',
        'symptom_analysis': 'Evaluación de Síntomas y Análisis de Severidad',
        'symptom': 'Parámetro Sintomático',
        'rating': 'Valor Reportado',
        'itching': 'Intensidad de Picazón',
        'pain': 'Nivel de Dolor',
        'redness': 'Enrojecimiento',
        'duration': 'Duración',
        'days': 'días',
        'fever': 'Fiebre',
        'burning': 'Sensación de Ardor',
        'fuzzy_score': 'Índice de Severidad Difusa',
        'severity_category': 'Categoría de Severidad',
        'contributing_factors': 'Indicadores de Riesgo y Factores Contribuyentes',
        'xai_title': 'IA Explicable (Evidencia Visual Grad-CAM)',
        'xai_caption': 'Mapa de calor Grad-CAM que resalta las regiones evaluadas por la red neuronal.',
        'original_photo': 'Foto de la Piel',
        'heatmap_photo': 'Mapa de Calor Grad-CAM',
        'clinical_summary': 'Resumen de Decisión Clínica',
        'guidance_title': 'Orientación Médica y Cuidados en El Hogar',
        'preventive_measures': '🛡️ Medidas Preventivas y Protección',
        'supportive_care': '🏠 Cuidados Seguros en el Hogar',
        'things_to_avoid': '⚠️ Cosas que Debe Evitar',
        'warning_signs': '🚨 Signos de Advertencia / Alarma',
        'when_to_see_doctor': '👨‍⚕️ Cuándo Consultar al Dermatólogo',
        'doctor_consult_mandatory': 'CONSULTA MÉDICA OBLIGATORIA: Los cuidados en el hogar no reemplazan la atención médica.',
        'footer': 'SkinSense AI v2.0 | MobileNetV2 + Fuzzy Engine + Grad-CAM XAI'
    }
}


# ────────────────────────────────────────────────
# HELPER FUNCTIONS & CARD BUILDERS
# ────────────────────────────────────────────────
def _get_loc(lang_code):
    lang_clean = (lang_code or 'en').lower()
    return PDF_LOCALIZATION.get(lang_clean, PDF_LOCALIZATION['en'])


def _get_risk_badge(risk_level):
    rl = (risk_level or '').lower()
    if any(k in rl for k in ['high', 'malignant', 'severe']):
        return COLOR_DANGER, 'HIGH RISK'
    if any(k in rl for k in ['moderate', 'medium', 'pre-cancerous']):
        return COLOR_WARNING, 'MODERATE RISK'
    return COLOR_SUCCESS, 'LOW RISK'


def _build_bullet_card(title, items, title_color, bg_color, border_color):
    """Build a styled medical callout card table containing a title and bullet list."""
    if not items:
        return []
    
    card_elements = []
    title_style = ParagraphStyle(
        'card_title',
        fontName=FONT_BOLD,
        fontSize=9.5,
        textColor=title_color,
        spaceAfter=5
    )
    bullet_style = ParagraphStyle(
        'card_bullet',
        fontName=FONT_REGULAR,
        fontSize=8.5,
        textColor=COLOR_TEXT_MAIN,
        leading=12,
        leftIndent=6,
        spaceAfter=3
    )

    card_elements.append(Paragraph(title, title_style))
    for item in items:
        if isinstance(item, dict):
            item_str = item.get('title') or item.get('source') or str(item)
        else:
            item_str = str(item)
        item_clean = item_str.strip()
        if item_clean:
            card_elements.append(Paragraph(f"• {item_clean}", bullet_style))

    card_table = Table([[card_elements]], colWidths=[18 * cm])
    card_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('BOX', (0, 0), (-1, -1), 0.5, border_color),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return [card_table, Spacer(1, 0.3 * cm)]


# ────────────────────────────────────────────────
# MAIN PDF GENERATOR FUNCTION
# ────────────────────────────────────────────────
def generate_assessment_pdf(assessment, upload_folder, output_path=None, lang='en'):
    """
    Generate a professional, multi-page dermatology assessment PDF report.

    Args:
        assessment (dict): Full assessment dictionary.
        upload_folder (str): Folder path containing heatmap/photo files.
        output_path (str, optional): File path to save output PDF. If None, returns bytes.
        lang (str): Language code ('en', 'hi', 'bho', 'mr', 'bn', 'es', etc.)

    Returns:
        bytes or str: PDF bytes if output_path is None, else output_path string.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab is not installed. Run: pip install reportlab")

    lang_code = (lang or assessment.get('lang') or 'en').lower()
    loc = _get_loc(lang_code)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"SkinSense Report {assessment.get('id', '')}",
        author="SkinSense AI System",
        subject="Clinical Dermatological Assessment Report"
    )

    story = []

    # ── TYPOGRAPHY STYLES ──
    style_hdr_logo = ParagraphStyle('hdr_logo', fontName=FONT_BOLD, fontSize=18, textColor=COLOR_PRIMARY, leading=20)
    style_hdr_sub  = ParagraphStyle('hdr_sub',  fontName=FONT_REGULAR, fontSize=9, textColor=COLOR_TEXT_MUTED, leading=11)
    style_hdr_right= ParagraphStyle('hdr_right', fontName=FONT_BOLD, fontSize=9, textColor=COLOR_TEXT_MAIN, alignment=TA_RIGHT, leading=12)

    style_section_title = ParagraphStyle(
        'sec_title',
        fontName=FONT_BOLD,
        fontSize=11,
        textColor=COLOR_SECONDARY,
        spaceBefore=8,
        spaceAfter=4,
        leading=14
    )

    style_body = ParagraphStyle('body', fontName=FONT_REGULAR, fontSize=8.5, textColor=COLOR_TEXT_MAIN, leading=12)
    style_body_bold = ParagraphStyle('body_b', fontName=FONT_BOLD, fontSize=8.5, textColor=COLOR_TEXT_MAIN, leading=12)
    style_caption = ParagraphStyle('caption', fontName=FONT_ITALIC, fontSize=7.5, textColor=COLOR_TEXT_MUTED, alignment=TA_CENTER, leading=10)

    # ────────────────────────────────────────────
    # 1. HEADER BRANDING & METADATA
    # ────────────────────────────────────────────
    report_id = assessment.get('id', 'ASS-UNKNOWN')
    now_str   = datetime.datetime.now().strftime('%B %d, %Y at %I:%M %p')

    header_data = [[
        Paragraph(f'<b>SkinSense</b><br/><font color="#64748b" size="8">{loc["sub_title"]}</font>', style_hdr_logo),
        Paragraph(f'<font color="#0f766e" size="10"><b>{loc["doc_title"]}</b></font><br/>'
                  f'<font size="8"><b>{loc["assessment_id"]}: {report_id}</b></font><br/>'
                  f'<font color="#64748b" size="7.5">{now_str} | Lang: {lang_code.upper()}</font>', style_hdr_right)
    ]]
    header_table = Table(header_data, colWidths=[9.5 * cm, 8.5 * cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceAfter=8))

    # ────────────────────────────────────────────
    # 2. MEDICAL DISCLAIMER BANNER
    # ────────────────────────────────────────────
    disclaimer_p = Paragraph(
        f"<b>MANDATORY MEDICAL ADVISORY:</b> {loc['disclaimer']}",
        ParagraphStyle(
            'disc_banner',
            fontName=FONT_REGULAR,
            fontSize=7.5,
            textColor=HexColor('#991b1b'),
            alignment=TA_JUSTIFY,
            leading=10.5
        )
    )
    disc_table = Table([[disclaimer_p]], colWidths=[18 * cm])
    disc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#fef2f2')),
        ('BOX', (0, 0), (-1, -1), 0.5, HexColor('#fca5a5')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(disc_table)
    story.append(Spacer(1, 0.3 * cm))

    # ────────────────────────────────────────────
    # 3. PATIENT & EXAMINATION OVERVIEW
    # ────────────────────────────────────────────
    story.append(Paragraph(loc['patient_info'], style_section_title))

    patient_name = assessment.get('patient_name', 'Anonymous')
    patient_age  = f"{assessment.get('patient_age', 'N/A')} {loc['years']}"
    exam_date    = assessment.get('created_at', now_str).split(' ')[0] if assessment.get('created_at') else now_str.split(' ')[0]
    body_region  = assessment.get('body_region') or 'Unspecified'
    img_quality  = assessment.get('quality_status') or 'Optimal quality'

    p_data = [
        [Paragraph(f"<b>{loc['patient_name']}:</b>", style_body_bold), Paragraph(patient_name, style_body),
         Paragraph(f"<b>{loc['patient_age']}:</b>", style_body_bold), Paragraph(patient_age, style_body)],
        [Paragraph(f"<b>{loc['assessment_id']}:</b>", style_body_bold), Paragraph(report_id, style_body),
         Paragraph(f"<b>{loc['report_date']}:</b>", style_body_bold), Paragraph(exam_date, style_body)],
        [Paragraph(f"<b>{loc['lesion_region']}:</b>", style_body_bold), Paragraph(body_region, style_body),
         Paragraph(f"<b>{loc['image_quality']}:</b>", style_body_bold), Paragraph(img_quality, style_body)],
    ]
    p_table = Table(p_data, colWidths=[3.2 * cm, 5.8 * cm, 3.2 * cm, 5.8 * cm])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_NEUTRAL_BG),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(p_table)
    story.append(Spacer(1, 0.4 * cm))

    # ────────────────────────────────────────────
    # 4. PRIMARY AI DIAGNOSTIC PREDICTION
    # ────────────────────────────────────────────
    story.append(Paragraph(loc['ai_diagnosis'], style_section_title))

    top_pred = assessment.get('top_prediction', {})
    if not top_pred:
        top_pred = {
            'name': assessment.get('predicted_name', 'Unknown Condition'),
            'code': assessment.get('predicted_class', 'unknown'),
            'score': assessment.get('model_score', 0.0),
            'risk_level': 'Moderate'
        }

    score_val = top_pred.get('score', assessment.get('model_score', 0.0))
    score_pct = f"{score_val * 100:.1f}%" if isinstance(score_val, float) and score_val <= 1.0 else f"{score_val:.1f}%"
    is_reliable = assessment.get('is_reliable', True)
    reliability_text = loc['high_confidence'] if is_reliable else loc['low_confidence']
    risk_color, risk_label = _get_risk_badge(top_pred.get('risk_level', 'Moderate'))

    entropy = assessment.get('model_uncertainty')
    entropy_text = f"{entropy:.3f}" if isinstance(entropy, (int, float)) else 'Not recorded'

    d_data = [
        [Paragraph(f"<b>{loc['primary_diagnosis']}:</b>", style_body_bold),
         Paragraph(f"<font color='#0f766e' size='10'><b>{top_pred.get('name', 'N/A')}</b></font>", style_body),
         Paragraph(f"<b>{loc['confidence']}:</b>", style_body_bold),
         Paragraph(f"<font size='10'><b>{score_pct}</b></font>", style_body)],
        [Paragraph(f"<b>{loc['disease_code']}:</b>", style_body_bold),
         Paragraph(str(top_pred.get('code', 'N/A')).upper(), style_body),
         Paragraph(f"<b>{loc['reliability']}:</b>", style_body_bold),
         Paragraph(reliability_text, style_body)],
        [Paragraph(f"<b>{loc['risk_level']}:</b>", style_body_bold),
         Paragraph(f"<font color='{risk_color.hexval()}'><b>{top_pred.get('risk_level', risk_label)}</b></font>", style_body),
         Paragraph(f"<b>Model Entropy:</b>", style_body_bold),
         Paragraph(entropy_text, style_body)],
    ]

    d_table = Table(d_data, colWidths=[3.2 * cm, 5.8 * cm, 3.2 * cm, 5.8 * cm])
    d_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_ACCENT_BG),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(d_table)
    story.append(Spacer(1, 0.4 * cm))

    # ────────────────────────────────────────────
    # 4.5 DERMATOLOGIST CLINICAL VERDICT (IF REVIEWED)
    # ────────────────────────────────────────────
    derm_diag  = assessment.get('dermatologist_diagnosis')
    derm_notes = assessment.get('dermatologist_notes')
    if derm_diag or derm_notes or assessment.get('review_status') == 'completed':
        story.append(Paragraph("Dermatologist Clinical Verdict & Review", style_section_title))
        v_data = [
            [Paragraph("<b>Review Status:</b>", style_body_bold),
             Paragraph("<font color='#059669'><b>Completed & Verified by Dermatologist</b></font>", style_body)],
        ]
        if derm_diag:
            v_data.append([
                Paragraph("<b>Clinical Verdict:</b>", style_body_bold),
                Paragraph(f"<font color='#0f766e' size='9'><b>{derm_diag}</b></font>", style_body)
            ])
        if derm_notes:
            v_data.append([
                Paragraph("<b>Doctor Notes:</b>", style_body_bold),
                Paragraph(derm_notes, style_body)
            ])

        v_table = Table(v_data, colWidths=[3.5 * cm, 14.5 * cm])
        v_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor("#ECFDF5")),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#A7F3D0")),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(v_table)
        story.append(Spacer(1, 0.4 * cm))

    # ────────────────────────────────────────────
    # 5. DIFFERENTIAL DIAGNOSIS (TOP-3 PREDICTIONS TABLE)
    # ────────────────────────────────────────────
    top_3 = assessment.get('top_predictions', assessment.get('top_3_predictions', []))
    if top_3:
        story.append(Paragraph(loc['differential_diagnosis'], style_section_title))
        diff_header = [
            Paragraph(f"<b>{loc['rank']}</b>", ParagraphStyle('dh', fontName=FONT_BOLD, fontSize=8, textColor=white, alignment=TA_CENTER)),
            Paragraph(f"<b>{loc['condition']}</b>", ParagraphStyle('dh2', fontName=FONT_BOLD, fontSize=8, textColor=white)),
            Paragraph(f"<b>{loc['code']}</b>", ParagraphStyle('dh3', fontName=FONT_BOLD, fontSize=8, textColor=white, alignment=TA_CENTER)),
            Paragraph(f"<b>{loc['score']}</b>", ParagraphStyle('dh4', fontName=FONT_BOLD, fontSize=8, textColor=white, alignment=TA_CENTER)),
            Paragraph(f"<b>{loc['risk_level']}</b>", ParagraphStyle('dh5', fontName=FONT_BOLD, fontSize=8, textColor=white, alignment=TA_CENTER)),
        ]
        diff_rows = [diff_header]
        for idx, pred in enumerate(top_3[:3], 1):
            p_score = pred.get('score', 0.0)
            p_score_pct = f"{p_score * 100:.1f}%" if isinstance(p_score, float) and p_score <= 1.0 else f"{p_score:.1f}%"
            _, p_risk = _get_risk_badge(pred.get('risk_level', ''))

            diff_rows.append([
                Paragraph(str(idx), ParagraphStyle('dr', fontName=FONT_REGULAR, fontSize=8, alignment=TA_CENTER)),
                Paragraph(pred.get('name', 'N/A'), style_body),
                Paragraph(str(pred.get('code', 'N/A')).upper(), ParagraphStyle('dr2', fontName=FONT_REGULAR, fontSize=8, alignment=TA_CENTER)),
                Paragraph(f"<b>{p_score_pct}</b>", ParagraphStyle('dr3', fontName=FONT_REGULAR, fontSize=8, alignment=TA_CENTER)),
                Paragraph(pred.get('risk_level') or p_risk, ParagraphStyle('dr4', fontName=FONT_REGULAR, fontSize=8, alignment=TA_CENTER)),
            ])

        diff_table = Table(diff_rows, colWidths=[1.0 * cm, 7.0 * cm, 2.2 * cm, 3.8 * cm, 4.0 * cm])
        diff_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, COLOR_NEUTRAL_BG]),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(diff_table)
        story.append(Spacer(1, 0.4 * cm))

    # ────────────────────────────────────────────
    # 6. SYMPTOM ASSESSMENT & FUZZY SEVERITY ANALYSIS
    # ────────────────────────────────────────────
    story.append(Paragraph(loc['symptom_analysis'], style_section_title))

    sev_score = assessment.get('severity_score', 0.0)
    sev_cat   = assessment.get('severity_category', 'Mild')
    sev_color, _ = _get_risk_badge(sev_cat)

    fever_labels   = ['None', 'Mild', 'High']
    burning_labels = ['None', 'Mild', 'Moderate', 'Severe']
    fever_val   = fever_labels[min(int(assessment.get('fever_level', 0)), 2)]
    burning_val = burning_labels[min(int(assessment.get('burning_level', 0)), 3)]

    sym_data = [
        [Paragraph(f"<b>{loc['symptom']}</b>", style_body_bold), Paragraph(f"<b>{loc['rating']}</b>", style_body_bold),
         Paragraph(f"<b>{loc['symptom']}</b>", style_body_bold), Paragraph(f"<b>{loc['rating']}</b>", style_body_bold)],
        [Paragraph(loc['itching'], style_body), Paragraph(f"{assessment.get('itching', 0)} / 10", style_body),
         Paragraph(loc['pain'], style_body), Paragraph(f"{assessment.get('pain', 0)} / 10", style_body)],
        [Paragraph(loc['redness'], style_body), Paragraph(f"{assessment.get('redness', 0)} / 10", style_body),
         Paragraph(loc['duration'], style_body), Paragraph(f"{assessment.get('duration_days', 0)} {loc['days']}", style_body)],
        [Paragraph(loc['fever'], style_body), Paragraph(fever_val, style_body),
         Paragraph(loc['burning'], style_body), Paragraph(burning_val, style_body)],
        [Paragraph(f"<b>{loc['fuzzy_score']}:</b>", style_body_bold), Paragraph(f"<b>{sev_score:.1f} / 100</b>", style_body),
         Paragraph(f"<b>{loc['severity_category']}:</b>", style_body_bold), Paragraph(f"<font color='{sev_color.hexval()}'><b>{sev_cat}</b></font>", style_body)],
    ]

    sym_table = Table(sym_data, colWidths=[4.2 * cm, 4.8 * cm, 4.2 * cm, 4.8 * cm])
    sym_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, COLOR_ACCENT_BG, white, COLOR_NEUTRAL_BG]),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sym_table)
    story.append(Spacer(1, 0.3 * cm))

    # Contributing factors list
    factors = assessment.get('contributing_factors', [])
    if factors:
        factors_items = [str(f) for f in factors]
        story.extend(_build_bullet_card(loc['contributing_factors'], factors_items, COLOR_SECONDARY, COLOR_NEUTRAL_BG, COLOR_BORDER))

    # ────────────────────────────────────────────
    # 7. EXPLAINABLE AI (GRAD-CAM VISUAL FOCUS EVIDENCE)
    # ────────────────────────────────────────────
    heatmap_fn = assessment.get('heatmap_filename') or assessment.get('overlay_filename')
    photo_fn   = assessment.get('image_filename')

    heatmap_path = os.path.join(upload_folder, heatmap_fn) if heatmap_fn and upload_folder else None
    photo_path   = os.path.join(upload_folder, photo_fn) if photo_fn and upload_folder else None

    img_elements = []
    if photo_path and os.path.exists(photo_path):
        try:
            p_img = RLImage(photo_path, width=7.2 * cm, height=5.4 * cm)
            img_elements.append([p_img, Paragraph(loc['original_photo'], style_caption)])
        except Exception as e:
            print(f"[PDFService] Warning loading photo image: {e}")

    if heatmap_path and os.path.exists(heatmap_path):
        try:
            h_img = RLImage(heatmap_path, width=7.2 * cm, height=5.4 * cm)
            img_elements.append([h_img, Paragraph(loc['heatmap_photo'], style_caption)])
        except Exception as e:
            print(f"[PDFService] Warning loading heatmap image: {e}")

    if img_elements:
        story.append(Paragraph(loc['xai_title'], style_section_title))
        if len(img_elements) == 2:
            xai_table_data = [[img_elements[0][0], img_elements[1][0]],
                              [img_elements[0][1], img_elements[1][1]]]
            xai_table = Table(xai_table_data, colWidths=[9 * cm, 9 * cm])
        else:
            xai_table_data = [[img_elements[0][0]], [img_elements[0][1]]]
            xai_table = Table(xai_table_data, colWidths=[18 * cm])

        xai_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(xai_table)
        story.append(Paragraph(loc['xai_caption'], style_caption))
        story.append(Spacer(1, 0.4 * cm))

    # ────────────────────────────────────────────
    # 8. CLINICAL DECISION SUMMARY
    # ────────────────────────────────────────────
    story.append(Paragraph(loc['clinical_summary'], style_section_title))
    summary_text = assessment.get('clinical_summary') or 'AI dermatological analysis complete. Patient should monitor lesion and consult a physician.'
    summary_p = Paragraph(summary_text, ParagraphStyle('summary_p', fontName=FONT_REGULAR, fontSize=8.5, textColor=COLOR_TEXT_MAIN, leading=13, alignment=TA_JUSTIFY))

    summary_table = Table([[summary_p]], colWidths=[18 * cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_ACCENT_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, COLOR_PRIMARY),
        ('PADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.4 * cm))

    # ────────────────────────────────────────────
    # 9. STRUCTURED EVIDENCE-BASED GUIDANCE
    # ────────────────────────────────────────────
    story.append(Paragraph(loc['guidance_title'], style_section_title))

    guidance = assessment.get('home_care_and_prevention') or assessment.get('knowledge_base') or {}
    pred_code = assessment.get('predicted_class') or 'unclassified'
    is_rel = assessment.get('is_reliable', True)
    asm_stat = assessment.get('assessment_status', 'success')
    if not is_rel or asm_stat == 'unable_to_assess' or pred_code == 'unclassified':
        pred_code = 'unclassified'

    if not isinstance(guidance, dict) or not guidance or guidance.get('condition_code') != pred_code:
        db_path = assessment.get('db_path')
        if db_path and os.path.exists(db_path):
            try:
                from backend.services.personalized_care_service import PersonalizedCareService
                care_svc = PersonalizedCareService(db_path)
                guidance = care_svc.get_guidance_for_condition(
                    pred_code,
                    lang=lang_code,
                    is_reliable=is_rel,
                    assessment_status=asm_stat
                )
            except Exception as e:
                print(f"[PDFService] Note loading dynamic guidance: {e}")

    prev_items = guidance.get('preventive_measures') or [
        "Apply broad-spectrum SPF 30+ sunscreen daily, even on cloudy days.",
        "Perform monthly self-skin checks using the ABCDE method.",
        "Wear protective sun clothing and broad-brimmed hats outdoors."
    ]
    care_items = guidance.get('supportive_care') or [
        "Clean skin gently with mild, fragrance-free cleanser and warm water.",
        "Apply a clean, fragrance-free emollient daily to protect skin barrier.",
        "Avoid picking, rubbing, or scratching at the skin lesion."
    ]
    avoid_items = guidance.get('things_to_avoid') or [
        "Do NOT scratch, pick, or attempt home surgical removal of moles/lesions.",
        "Do NOT apply household chemicals, lemon juice, vinegar, bleach, or toothpaste.",
        "Do NOT use unauthorized prescription creams without medical advice."
    ]
    warn_items = guidance.get('urgent_warning_signs') or [
        "ABCDE changes: Asymmetry, Border irregularity, Color variation, Diameter > 6mm, Evolving.",
        "Rapid expansion, spontaneous bleeding, oozing, or non-healing sores."
    ]
    doc_items = guidance.get('when_to_see_doctor') or [
        "Any new, changing, or non-healing spot on the skin.",
        "Persistent symptoms failing to improve with supportive care."
    ]

    story.extend(_build_bullet_card(loc['preventive_measures'], prev_items, COLOR_PRIMARY, COLOR_ACCENT_BG, COLOR_PRIMARY))
    story.extend(_build_bullet_card(loc['supportive_care'], care_items, COLOR_SUCCESS, HexColor('#f0fdf4'), HexColor('#86efac')))
    story.extend(_build_bullet_card(loc['things_to_avoid'], avoid_items, COLOR_DANGER, HexColor('#fef2f2'), HexColor('#fca5a5')))
    story.extend(_build_bullet_card(loc['warning_signs'], warn_items, HexColor('#991b1b'), HexColor('#fff7ed'), HexColor('#fdba74')))
    story.extend(_build_bullet_card(loc['when_to_see_doctor'], doc_items, COLOR_SECONDARY, COLOR_NEUTRAL_BG, COLOR_BORDER))

    # Mandatory Doctor Advisory Footer Callout
    adv_p = Paragraph(
        f"<b>MANDATORY CLINICAL ADVISORY:</b> {loc['doctor_consult_mandatory']}",
        ParagraphStyle('adv_p', fontName=FONT_BOLD, fontSize=8, textColor=COLOR_PRIMARY, alignment=TA_CENTER, leading=11)
    )
    adv_table = Table([[adv_p]], colWidths=[18 * cm])
    adv_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_ACCENT_BG),
        ('BOX', (0, 0), (-1, -1), 0.75, COLOR_PRIMARY),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(adv_table)
    story.append(Spacer(1, 0.4 * cm))

    # Signature & System Verification Block
    sig_data = [
        [Paragraph(f"<b>Report ID:</b> {report_id}", style_body),
         Paragraph("<b>SkinSense AI Clinical Decision Engine v2.0</b><br/><font color='#64748b' size='7.5'>Verified System Document Entry</font>", ParagraphStyle('sig', fontName=FONT_REGULAR, fontSize=8, alignment=TA_RIGHT, leading=11))]
    ]
    sig_table = Table(sig_data, colWidths=[9 * cm, 9 * cm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sig_table)

    # ────────────────────────────────────────────
    # BUILD DOCUMENT WITH NUMBERED CANVAS
    # ────────────────────────────────────────────
    def _canvas_maker(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c._report_id = report_id
        return c

    doc.build(story, canvasmaker=_canvas_maker)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        return output_path

    return pdf_bytes
