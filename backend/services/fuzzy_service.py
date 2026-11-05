class FuzzySeverityEngine:
    """Score reported symptoms using monotonic fuzzy membership and rules."""

    @staticmethod
    def _ramp(value, start, full):
        return max(0.0, min(1.0, (value - start) / (full - start)))

    def evaluate(self, itching, pain, redness, duration, fever, burning):
        itching = max(0, min(10, float(itching)))
        pain = max(0, min(10, float(pain)))
        redness = max(0, min(10, float(redness)))
        duration = max(0, min(60, float(duration)))
        fever = max(0, min(2, int(fever)))
        burning = max(0, min(3, int(burning)))

        membership = {
            name: {
                'at_least_moderate': self._ramp(value, 2, 5),
                'high': self._ramp(value, 6, 9),
            }
            for name, value in {'itching': itching, 'pain': pain, 'redness': redness}.items()
        }
        membership['duration'] = {'persistent': self._ramp(duration, 20, 60)}
        membership['fever'] = {'present': float(fever >= 1), 'high': float(fever == 2)}
        membership['burning'] = {'at_least_moderate': float(burning >= 2), 'severe': float(burning == 3)}

        itch = membership['itching']
        ache = membership['pain']
        red = membership['redness']
        # A baseline covers every input combination, including cases with no specific rule.
        baseline = (
            25 * itching / 10 + 25 * pain / 10 + 20 * redness / 10
            + 10 * duration / 60 + 10 * fever / 2 + 10 * burning / 3
        )
        rules = [
            ('R1', 'Combined symptom burden', baseline / 100, 100),
            ('R2', 'High itching or redness', max(itch['high'], red['high']), 50),
            ('R3', 'High pain or severe burning', max(ache['high'], membership['burning']['severe']), 90),
            ('R4', 'High reported fever', membership['fever']['high'], 70),
            ('R5', 'Persistent symptoms with high itching', min(membership['duration']['persistent'], itch['high']), 60),
            ('R6', 'At least moderate pain and redness', min(ache['at_least_moderate'], red['at_least_moderate']), 50),
            ('R7', 'At least moderate burning and pain', min(membership['burning']['at_least_moderate'], ache['at_least_moderate']), 50),
            ('R8', 'Reported fever with high redness', min(membership['fever']['present'], red['high']), 85),
        ]

        # Each rule raises a score floor in proportion to its activation.
        # Taking the maximum keeps a milder rule from diluting a stronger one.
        severity_score = round(max(strength * target for _, _, strength, target in rules), 2)
        activated_rules = [
            {
                'id': rule_id,
                'condition': condition,
                'consequent': f'Score floor up to {target}/100',
                'firing_strength': round(strength, 4),
                'score_contribution': round(strength * target, 2),
            }
            for rule_id, condition, strength, target in rules if strength > 0
        ]
        activated_rules.sort(key=lambda rule: rule['score_contribution'], reverse=True)

        if severity_score < 35:
            category = 'Mild'
        elif severity_score < 70:
            category = 'Moderate'
        else:
            category = 'High'

        contributing_factors = []
        # Determine Contributing Factors
        if itching >= 6:
            contributing_factors.append(f"High Itching Intensity ({itching}/10)")
        if pain >= 6:
            contributing_factors.append(f"Severe Pain Level ({pain}/10)")
        if redness >= 6:
            contributing_factors.append(f"Significant Erythema/Redness ({redness}/10)")
        if duration >= 21:
            contributing_factors.append(f"Chronic Duration ({int(duration)} days)")
        if fever >= 1:
            fever_str = "Mild" if fever == 1 else "High"
            contributing_factors.append(f"Systemic Fever Present ({fever_str})")
        if burning >= 2:
            burn_str = "Moderate" if burning == 2 else "Severe"
            contributing_factors.append(f"Burning Sensation ({burn_str})")

        if not contributing_factors:
            contributing_factors.append("No individual symptom crossed a contributing-factor threshold.")

        return {
            'severity_score': severity_score,
            'category': category,
            'contributing_factors': contributing_factors,
            'input_vector': {
                'itching': itching, 'pain': pain, 'redness': redness,
                'duration': duration, 'fever': fever, 'burning': burning,
            },
            'membership_levels': membership,
            'activated_rules': activated_rules,
            'disclaimer': 'Symptom severity is an estimate for review prioritization and does not establish a diagnosis.',
        }

    @staticmethod
    def explain(result):
        return {
            'input_values': result['input_vector'],
            'membership_levels': result['membership_levels'],
            'activated_rules': result['activated_rules'],
            'total_activated_rules': len(result['activated_rules']),
            'defuzzification_method': 'Maximum of activation-weighted rule scores',
            'severity_score': result['severity_score'],
            'severity_category': result['category'],
            'disclaimer': result['disclaimer'],
        }
