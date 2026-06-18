import json
import math
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import role_required
from professors.models import ProfessorProfile
from students.models import StudentProfile, StudentReference
from soutenances.models import (
    DefenseSchedule, Evaluation, Jury, JuryStudent, PFERequest, Result,
)

FILIERES = ['DS', 'FINTECH', 'LGTR', 'RXTL', 'MAEF', 'MAN']


def _mention(avg):
    if avg is None:
        return '-'
    if avg >= 18:
        return 'Excellent'
    if avg >= 16:
        return 'Tres bien'
    if avg >= 14:
        return 'Bien'
    if avg >= 12:
        return 'Passable'
    return 'Insuffisant'


def _mention_display(avg):
    if avg is None:
        return '-'
    if avg >= 18:
        return 'Excellent'
    if avg >= 16:
        return 'Tres bien'
    if avg >= 14:
        return 'Bien'
    if avg >= 12:
        return 'Passable'
    return 'Insuffisant'


def _charge_label(count):
    if count <= 3:
        return 'Faible'
    if count <= 6:
        return 'Moderee'
    if count <= 9:
        return 'Elevee'
    return 'Tres elevee'


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Global
# ─────────────────────────────────────────────────────────────────────────────
def _compute_global():
    total_ref = StudentReference.objects.count()
    total_profiles = StudentProfile.objects.count()
    total_sans_compte = max(total_ref - total_profiles, 0)
    total_demandes = PFERequest.objects.count()
    total_acceptees = PFERequest.objects.filter(status='accepted').count()

    accepted_ids = set(
        PFERequest.objects.filter(status='accepted').values_list('student_id', flat=True)
    )
    jury_ids = set(JuryStudent.objects.values_list('student_id', flat=True))
    sans_jury_ids = accepted_ids - jury_ids
    acceptes_sans_jury_count = len(sans_jury_ids)

    val_encadrant = PFERequest.objects.filter(
        status__in=['pending_admin', 'accepted', 'refused_by_admin']
    ).count()
    jury_count = JuryStudent.objects.count()
    schedule_count = DefenseSchedule.objects.count()
    result_published = Result.objects.filter(is_published=True).count()

    base = total_ref if total_ref > 0 else 1
    workflow = [
        {'label': 'Liste officielle',    'count': total_ref,        'pct': 100},
        {'label': 'Compte cree',         'count': total_profiles,   'pct': round(total_profiles / base * 100, 1)},
        {'label': 'Demande deposee',     'count': total_demandes,   'pct': round(total_demandes / base * 100, 1)},
        {'label': 'Valid. encadrant',    'count': val_encadrant,    'pct': round(val_encadrant / base * 100, 1)},
        {'label': 'Valid. admin',        'count': total_acceptees,  'pct': round(total_acceptees / base * 100, 1)},
        {'label': 'Jury affecte',        'count': jury_count,       'pct': round(jury_count / base * 100, 1)},
        {'label': 'Planning',            'count': schedule_count,   'pct': round(schedule_count / base * 100, 1)},
        {'label': 'Resultat publie',     'count': result_published, 'pct': round(result_published / base * 100, 1)},
    ]

    filiere_stats = []
    for f in FILIERES:
        off = StudentReference.objects.filter(filiere=f).count()
        ins = StudentProfile.objects.filter(filiere=f).count()
        sans = max(off - ins, 0)
        taux = round(ins / off * 100, 1) if off > 0 else 0
        filiere_stats.append({'filiere': f, 'officiels': off, 'inscrits': ins, 'sans_compte': sans, 'taux': taux})

    non_deposee = max(total_profiles - total_demandes, 0)
    pend_prof = PFERequest.objects.filter(status='pending_professor').count()
    pend_admin = PFERequest.objects.filter(status='pending_admin').count()
    refusee = PFERequest.objects.filter(status__in=['refused_by_professor', 'refused_by_admin']).count()

    statut_labels = ['Non deposee', 'Att. encadrant', 'Att. admin', 'Acceptee', 'Refusee']
    statut_values = [non_deposee, pend_prof, pend_admin, total_acceptees, refusee]
    statut_total = sum(statut_values)

    alertes = []
    if total_sans_compte > 0:
        alertes.append({'level': 'warning', 'msg': f"{total_sans_compte} etudiant(s) officiel(s) sans compte cree"})
    if pend_prof > 0:
        alertes.append({'level': 'warning', 'msg': f"{pend_prof} demande(s) bloquee(s) chez l'encadrant"})
    if pend_admin > 0:
        alertes.append({'level': 'warning', 'msg': f"{pend_admin} demande(s) bloquee(s) chez l'administration"})
    if acceptes_sans_jury_count > 0:
        alertes.append({'level': 'danger', 'msg': f"{acceptes_sans_jury_count} etudiant(s) accepte(s) sans jury affecte"})
    jurys_brouillon = Jury.objects.filter(is_validated=False).count()
    if jurys_brouillon > 0:
        alertes.append({'level': 'info', 'msg': f"{jurys_brouillon} jury(s) brouillon non publie(s)"})
    sans_planning = JuryStudent.objects.filter(schedule__isnull=True).count()
    if sans_planning > 0:
        alertes.append({'level': 'info', 'msg': f"{sans_planning} soutenance(s) sans planning defini"})
    res_non_pub = Result.objects.filter(is_published=False, average__isnull=False).count()
    if res_non_pub > 0:
        alertes.append({'level': 'info', 'msg': f"{res_non_pub} resultat(s) calcule(s) non publie(s)"})

    acceptes_sans_jury_list = []
    for sp in StudentProfile.objects.filter(id__in=list(sans_jury_ids)).select_related('encadrant').prefetch_related('pfe_request')[:20]:
        req = getattr(sp, 'pfe_request', None)
        delta = None
        if req and req.admin_reviewed_at:
            delta = (timezone.now() - req.admin_reviewed_at).days
        acceptes_sans_jury_list.append({
            'name': sp.full_name,
            'filiere': sp.filiere or '-',
            'encadrant': sp.encadrant.full_name if sp.encadrant_id else '-',
            'anciennete': f"{delta}j" if delta is not None else '-',
            'priorite': 'Haute' if delta and delta > 7 else 'Normale',
        })

    # synthese_encadrants: source officielle = StudentReference.encadrant_name (49 encadrants)
    enc_ref_data = defaultdict(lambda: {'mats': set(), 'by_f': {f: 0 for f in FILIERES}})
    for ref in StudentReference.objects.exclude(encadrant_name='').values('encadrant_name', 'matricule', 'filiere'):
        d = enc_ref_data[ref['encadrant_name']]
        d['mats'].add(ref['matricule'])
        if ref['filiere'] in FILIERES:
            d['by_f'][ref['filiere']] += 1

    mat_to_pid = {sp['matricule']: sp['id'] for sp in StudentProfile.objects.values('matricule', 'id')}
    pfe_status_map = {pr['student_id']: pr['status'] for pr in PFERequest.objects.values('student_id', 'status')}

    synthese_encadrants = []
    for enc_name, d in sorted(enc_ref_data.items(), key=lambda x: -len(x[1]['mats'])):
        mats = d['mats']
        total = len(mats)
        by_f = d['by_f']
        stud_ids = [mat_to_pid[m] for m in mats if m in mat_to_pid]
        pend_enc = sum(1 for sid in stud_ids if pfe_status_map.get(sid) == 'pending_professor')
        pend_adm = sum(1 for sid in stud_ids if pfe_status_map.get(sid) == 'pending_admin')
        acc = sum(1 for sid in stud_ids if pfe_status_map.get(sid) == 'accepted')
        sj = sum(1 for sid in stud_ids if sid in sans_jury_ids)
        taux = round(acc / total * 100, 1)
        synthese_encadrants.append({
            'prof': enc_name,
            'total': total,
            'by_f': by_f,
            'pend_enc': pend_enc,
            'pend_adm': pend_adm,
            'acc': acc,
            'sans_jury': sj,
            'taux': taux,
        })

    return {
        'total_ref': total_ref,
        'total_profiles': total_profiles,
        'total_sans_compte': total_sans_compte,
        'total_demandes': total_demandes,
        'total_acceptees': total_acceptees,
        'acceptes_sans_jury_count': acceptes_sans_jury_count,
        'workflow': workflow,
        'filiere_stats': filiere_stats,
        'statut_labels_json': json.dumps(statut_labels),
        'statut_values_json': json.dumps(statut_values),
        'statut_total': statut_total,
        'alertes': alertes,
        'acceptes_sans_jury_list': acceptes_sans_jury_list,
        'synthese_encadrants': synthese_encadrants,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Encadrants
#  Source officielle : StudentReference.encadrant_name (366 étudiants, 49 encadrants)
#  — utilise StudentProfile uniquement pour les données complémentaires
#    (statut demandes, jury) sur les étudiants inscrits.
# ─────────────────────────────────────────────────────────────────────────────
def _compute_encadrants():
    # Grouper les StudentReference par encadrant_name — source officielle
    refs_by_enc = (
        StudentReference.objects
        .exclude(encadrant_name='')
        .values('encadrant_name')
        .annotate(cnt=Count('matricule'))
        .order_by('-cnt')
    )

    actifs_count = refs_by_enc.count()
    total_ref = StudentReference.objects.exclude(encadrant_name='').count()
    charge_moyenne = round(total_ref / actifs_count, 1) if actifs_count else 0

    top = refs_by_enc.first()
    top_prof_name = top['encadrant_name'] if top else '-'
    top_prof_count = top['cnt'] if top else 0

    # Spécialité dominante sur la liste officielle (StudentReference)
    filiere_totals = {f: StudentReference.objects.filter(filiere=f).count() for f in FILIERES}
    total_with_filiere = sum(filiere_totals.values())
    spec_dominante = max(filiere_totals, key=filiere_totals.get) if any(filiere_totals.values()) else '-'
    spec_pct = round(filiere_totals.get(spec_dominante, 0) / total_with_filiere * 100, 1) if total_with_filiere else 0

    # Pré-charger toutes les répartitions par filière en une seule requête
    _all_refs_counts = (
        StudentReference.objects
        .exclude(encadrant_name='')
        .values('encadrant_name', 'filiere')
        .annotate(cnt=Count('matricule'))
    )
    all_enc_by_f = {}
    for item in _all_refs_counts:
        enc = item['encadrant_name']
        if enc not in all_enc_by_f:
            all_enc_by_f[enc] = {fi: 0 for fi in FILIERES}
        if item['filiere'] in FILIERES:
            all_enc_by_f[enc][item['filiere']] = item['cnt']

    encadrant_rows = []
    bar_labels = []
    bar_counts = []
    stacked_datasets_data = {f: [] for f in FILIERES}
    buckets = [0, 0, 0, 0]

    for row in refs_by_enc[:15]:
        enc_name = row['encadrant_name']
        total = row['cnt']

        by_f = all_enc_by_f.get(enc_name, {fi: 0 for fi in FILIERES})
        dominant = max(by_f, key=by_f.get) if any(by_f.values()) else '-'
        repart = [
            {'f': f, 'cnt': by_f[f], 'pct': round(by_f[f] / total * 100, 1) if total else 0}
            for f in FILIERES
        ]

        encadrant_rows.append({
            'prof': enc_name,
            'total': total,
            'dominant': dominant,
            'repart': repart,
            'by_f': by_f,
            'charge': _charge_label(total),
            'charge_level': 1 if total <= 3 else (2 if total <= 6 else (3 if total <= 9 else 4)),
        })
        bar_labels.append(enc_name)
        bar_counts.append(total)
        for f in FILIERES:
            stacked_datasets_data[f].append(by_f[f])

    # Tableau détail : TOUS les encadrants (pas seulement le top 15)
    enc_rows_all = []
    for row in refs_by_enc:
        enc_name = row['encadrant_name']
        total = row['cnt']
        by_f = all_enc_by_f.get(enc_name, {fi: 0 for fi in FILIERES})
        dominant = max(by_f, key=by_f.get) if any(by_f.values()) else '-'
        repart = [
            {'f': f, 'cnt': by_f[f], 'pct': round(by_f[f] / total * 100, 1) if total else 0}
            for f in FILIERES
        ]
        enc_rows_all.append({
            'prof': enc_name,
            'total': total,
            'dominant': dominant,
            'repart': repart,
            'by_f': by_f,
            'charge': _charge_label(total),
            'charge_level': 1 if total <= 3 else (2 if total <= 6 else (3 if total <= 9 else 4)),
        })

    # Équilibre de la charge sur tous les encadrants
    for row in refs_by_enc:
        c = row['cnt']
        if c <= 3:
            buckets[0] += 1
        elif c <= 6:
            buckets[1] += 1
        elif c <= 9:
            buckets[2] += 1
        else:
            buckets[3] += 1

    total_profs = sum(buckets)
    equilibre = [
        {'label': '1 - 3 etudiants', 'count': buckets[0], 'pct': round(buckets[0] / total_profs * 100) if total_profs else 0},
        {'label': '4 - 6 etudiants', 'count': buckets[1], 'pct': round(buckets[1] / total_profs * 100) if total_profs else 0},
        {'label': '7 - 9 etudiants', 'count': buckets[2], 'pct': round(buckets[2] / total_profs * 100) if total_profs else 0},
        {'label': '10+ etudiants',   'count': buckets[3], 'pct': round(buckets[3] / total_profs * 100) if total_profs else 0},
    ]

    filiere_colors = ['#0d9488', '#6ee7b7', '#3b82f6', '#a78bfa', '#fb923c', '#f472b6']

    stacked_datasets = [
        {'label': f, 'data': stacked_datasets_data[f], 'backgroundColor': filiere_colors[i]}
        for i, f in enumerate(FILIERES)
    ]

    # Tableau couverture par spécialité (top 15 uniquement, cohérent avec les graphiques)
    # enc_rows contient déjà by_f depuis StudentReference

    return {
        'enc_actifs_count': actifs_count,
        'enc_charge_moyenne': charge_moyenne,
        'enc_top_prof_name': top_prof_name,
        'enc_top_prof_count': top_prof_count,
        'enc_spec_dominante': spec_dominante,
        'enc_spec_pct': spec_pct,
        'enc_rows': encadrant_rows,
        'enc_rows_all': enc_rows_all,
        'enc_rows_all_count': len(enc_rows_all),
        'enc_bar_labels_json': json.dumps(bar_labels),
        'enc_bar_counts_json': json.dumps(bar_counts),
        'enc_stacked_json': json.dumps(stacked_datasets),
        'enc_stacked_labels_json': json.dumps(bar_labels),
        'enc_equilibre': equilibre,
        'enc_equilibre_json': json.dumps(buckets),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Entreprises
# ─────────────────────────────────────────────────────────────────────────────
def _compute_entreprises():
    students_with_ent = StudentProfile.objects.exclude(entreprise='')
    total_rattaches = students_with_ent.count()

    ent_agg = list(
        students_with_ent
        .values('entreprise')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    nb_entreprises = len(ent_agg)

    top = ent_agg[0] if ent_agg else None
    top_ent_name = top['entreprise'] if top else 'Non renseignee'
    top_ent_count = top['count'] if top else 0
    top_ent_pct = round(top_ent_count / total_rattaches * 100, 1) if total_rattaches else 0

    filiere_totals = {f: students_with_ent.filter(filiere=f).count() for f in FILIERES}
    spec_dom = max(filiere_totals, key=filiere_totals.get) if any(filiere_totals.values()) else '-'
    spec_dom_pct = round(filiere_totals.get(spec_dom, 0) / total_rattaches * 100, 1) if total_rattaches else 0

    FILIERES_COLORS = ['#0d9488', '#6ee7b7', '#3b82f6', '#a78bfa', '#fb923c', '#f472b6']

    # ── Pré-calcul groupé : répartition filière par entreprise ─────────────
    _ent_filiere_qs = (
        students_with_ent
        .values('entreprise', 'filiere')
        .annotate(cnt=Count('id'))
    )
    ent_by_f_all = {}
    for item in _ent_filiere_qs:
        e = item['entreprise']
        if e not in ent_by_f_all:
            ent_by_f_all[e] = {fi: 0 for fi in FILIERES}
        if item['filiere'] in FILIERES:
            ent_by_f_all[e][item['filiere']] = item['cnt']

    # ── Pré-calcul groupé : moyenne et nb soutenances par entreprise ────────
    _res_qs = (
        Result.objects
        .filter(is_published=True)
        .values('jury_student__student__entreprise')
        .annotate(avg=Avg('average'), nb=Count('id'))
    )
    ent_avgs_dict = {}
    ent_sout_dict = {}
    for item in _res_qs:
        e = item['jury_student__student__entreprise']
        if e:
            ent_avgs_dict[e] = item['avg']
            ent_sout_dict[e] = item['nb']

    # ── Top 15 pour graphiques + tableau croisé ─────────────────────────────
    bar_labels = []
    bar_counts = []
    entreprise_rows = []
    cross_data = []
    stacked_ent_datasets = {f: [] for f in FILIERES}

    for ent in ent_agg[:15]:
        name = ent['entreprise']
        cnt = ent['count']
        by_f = ent_by_f_all.get(name, {fi: 0 for fi in FILIERES})
        dominant = max(by_f, key=by_f.get) if any(by_f.values()) else '-'
        repart = [{'f': f, 'cnt': by_f[f], 'pct': round(by_f[f] / cnt * 100, 1) if cnt else 0} for f in FILIERES]
        avg_r = ent_avgs_dict.get(name)
        avg_str = f"{float(avg_r):.2f}" if avg_r else '—'
        soutenances = ent_sout_dict.get(name, 0)
        sout_pct = round(soutenances / cnt * 100, 1) if cnt else 0

        entreprise_rows.append({
            'name': name, 'count': cnt, 'dominant': dominant,
            'repart': repart, 'by_f': by_f,
            'avg': avg_str,
            'soutenances': f"{soutenances} ({sout_pct}%)",
        })
        bar_labels.append(name)
        bar_counts.append(cnt)
        for f in FILIERES:
            stacked_ent_datasets[f].append(by_f[f])
        cross_data.append({'name': name, 'by_f': by_f, 'total': cnt})

    stacked_ent_ds = [
        {'label': f, 'data': stacked_ent_datasets[f], 'backgroundColor': FILIERES_COLORS[i]}
        for i, f in enumerate(FILIERES)
    ]

    # ── Toutes les entreprises pour le tableau détail ───────────────────────
    ent_rows_all = []
    for ent in ent_agg:
        name = ent['entreprise']
        cnt = ent['count']
        by_f = ent_by_f_all.get(name, {fi: 0 for fi in FILIERES})
        dominant = max(by_f, key=by_f.get) if any(by_f.values()) else '-'
        repart = [{'f': f, 'cnt': by_f[f], 'pct': round(by_f[f] / cnt * 100, 1) if cnt else 0} for f in FILIERES]
        avg_r = ent_avgs_dict.get(name)
        avg_str = f"{float(avg_r):.2f}" if avg_r else '—'
        soutenances = ent_sout_dict.get(name, 0)
        sout_pct = round(soutenances / cnt * 100, 1) if cnt else 0
        ent_rows_all.append({
            'name': name, 'count': cnt, 'dominant': dominant,
            'repart': repart, 'by_f': by_f,
            'avg': avg_str,
            'soutenances': f"{soutenances} ({sout_pct}%)",
        })

    # ── Moyenne par entreprise pour le graphique (top 8) ────────────────────
    ent_avg_labels = []
    ent_avg_values = []
    for ent in ent_agg[:8]:
        name = ent['entreprise']
        avg_r = ent_avgs_dict.get(name)
        ent_avg_labels.append(name)
        ent_avg_values.append(round(float(avg_r), 2) if avg_r else None)

    moy_par_ent = round(total_rattaches / nb_entreprises, 1) if nb_entreprises else 0

    return {
        'ent_nb': nb_entreprises,
        'ent_total_rattaches': total_rattaches,
        'ent_top_name': top_ent_name,
        'ent_top_count': top_ent_count,
        'ent_top_pct': top_ent_pct,
        'ent_spec_dom': spec_dom,
        'ent_spec_dom_pct': spec_dom_pct,
        'ent_rows': entreprise_rows,
        'ent_rows_all': ent_rows_all,
        'ent_rows_all_count': len(ent_rows_all),
        'ent_bar_labels_json': json.dumps(bar_labels),
        'ent_bar_counts_json': json.dumps(bar_counts),
        'ent_stacked_json': json.dumps(stacked_ent_ds),
        'ent_stacked_labels_json': json.dumps(bar_labels),
        'ent_cross_data': cross_data,
        'ent_moy_par_ent': moy_par_ent,
        'ent_avg_labels_json': json.dumps(ent_avg_labels),
        'ent_avg_values_json': json.dumps(ent_avg_values),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Resultats
# ─────────────────────────────────────────────────────────────────────────────
def _compute_resultats():
    # Exclure les PFE déclarés non soutenables — pas de résultat valide
    pub_results = Result.objects.filter(
        is_published=True
    ).exclude(
        jury_student__pfe_soutenable_status='non_soutenable'
    ).select_related('jury_student__student')
    total_results = pub_results.count()
    global_avg_agg = pub_results.aggregate(a=Avg('average'))['a']
    global_avg_f = round(float(global_avg_agg), 2) if global_avg_agg else 0
    # Seuil réussite : moyenne >= 12 (Passable ou supérieur), conformément aux mentions
    passed = pub_results.filter(average__gte=12).count()
    taux_reussite = round(passed / total_results * 100, 1) if total_results else 0

    all_evals = Evaluation.objects.filter(is_submitted=True)
    avg_r_global = all_evals.aggregate(a=Avg('rapport_note'))['a'] or 0
    avg_p_global = all_evals.aggregate(a=Avg('presentation_note'))['a'] or 0
    avg_q_global = all_evals.aggregate(a=Avg('questions_note'))['a'] or 0
    comp_map = {'Rapport': float(avg_r_global), 'Presentation': float(avg_p_global), 'Questions': float(avg_q_global)}
    best_comp = max(comp_map, key=comp_map.get) if any(comp_map.values()) else '-'
    best_comp_avg = round(comp_map.get(best_comp, 0), 2)

    MENTION_KEYS = ['Excellent', 'Tres bien', 'Bien', 'Passable', 'Insuffisant']
    MENTION_COLORS = ['#0d9488', '#6ee7b7', '#84cc16', '#fb923c', '#ef4444']

    filiere_data = []
    bar_avgs = []
    bar_rapport = []
    bar_presentation = []
    bar_questions = []
    bar_std = []
    mentions_by_filiere = {k: [] for k in MENTION_KEYS}

    for f in FILIERES:
        f_results = pub_results.filter(jury_student__student__filiere=f)
        f_count = f_results.count()

        if f_count == 0:
            bar_avgs.append(0)
            bar_rapport.append(0)
            bar_presentation.append(0)
            bar_questions.append(0)
            bar_std.append(0)
            for k in MENTION_KEYS:
                mentions_by_filiere[k].append(0)
            filiere_data.append({
                'filiere': f, 'count': 0, 'avg': 0,
                'avg_rapport': 0, 'avg_pres': 0, 'avg_quest': 0,
                'taux': 0, 'mention': '-', 'std': 0,
            })
            continue

        avg = f_results.aggregate(a=Avg('average'))['a']
        avg_f = round(float(avg), 2) if avg else 0
        passed_f = f_results.filter(average__gte=12).count()
        taux_f = round(passed_f / f_count * 100, 1)

        js_ids = list(f_results.values_list('jury_student_id', flat=True))
        evals_f = Evaluation.objects.filter(jury_student_id__in=js_ids, is_submitted=True)
        avg_rp = round(float(evals_f.aggregate(a=Avg('rapport_note'))['a'] or 0), 2)
        avg_pr = round(float(evals_f.aggregate(a=Avg('presentation_note'))['a'] or 0), 2)
        avg_qu = round(float(evals_f.aggregate(a=Avg('questions_note'))['a'] or 0), 2)

        all_avgs = [float(r.average) for r in f_results if r.average is not None]
        if len(all_avgs) >= 2:
            mean = sum(all_avgs) / len(all_avgs)
            variance = sum((x - mean) ** 2 for x in all_avgs) / len(all_avgs)
            std = round(math.sqrt(variance), 2)
        else:
            std = 0

        mc = {'Excellent': 0, 'Tres bien': 0, 'Bien': 0, 'Passable': 0, 'Insuffisant': 0}
        for r in f_results:
            if r.average is None:
                continue
            a = float(r.average)
            if a >= 18:
                mc['Excellent'] += 1
            elif a >= 16:
                mc['Tres bien'] += 1
            elif a >= 14:
                mc['Bien'] += 1
            elif a >= 12:
                mc['Passable'] += 1
            else:
                mc['Insuffisant'] += 1

        dom_mention = max(mc, key=mc.get) if any(mc.values()) else '-'
        mc_pct = {k: round(v / f_count * 100) for k, v in mc.items()}

        bar_avgs.append(avg_f)
        bar_rapport.append(avg_rp)
        bar_presentation.append(avg_pr)
        bar_questions.append(avg_qu)
        bar_std.append(std)
        for k in MENTION_KEYS:
            mentions_by_filiere[k].append(mc_pct[k])

        filiere_data.append({
            'filiere': f, 'count': f_count, 'avg': avg_f,
            'avg_rapport': avg_rp, 'avg_pres': avg_pr, 'avg_quest': avg_qu,
            'taux': taux_f, 'mention': dom_mention, 'std': std,
        })

    best_f = max(filiere_data, key=lambda x: x['avg']) if filiere_data else None
    best_filiere = best_f['filiere'] if best_f else '-'
    best_avg = best_f['avg'] if best_f else 0

    mentions_ds = [
        {'label': k, 'data': mentions_by_filiere[k], 'backgroundColor': MENTION_COLORS[i]}
        for i, k in enumerate(MENTION_KEYS)
    ]

    return {
        'res_global_avg': global_avg_f,
        'res_taux_reussite': taux_reussite,
        'res_passed': passed,
        'res_total': total_results,
        'res_best_filiere': best_filiere,
        'res_best_avg': best_avg,
        'res_best_comp': best_comp,
        'res_best_comp_avg': best_comp_avg,
        'res_filiere_data': filiere_data,
        'res_bar_avgs_json': json.dumps(bar_avgs),
        'res_bar_rapport_json': json.dumps(bar_rapport),
        'res_bar_pres_json': json.dumps(bar_presentation),
        'res_bar_quest_json': json.dumps(bar_questions),
        'res_bar_std_json': json.dumps(bar_std),
        'res_mentions_ds_json': json.dumps(mentions_ds),
        'res_filieres_json': json.dumps(FILIERES),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Main view
# ─────────────────────────────────────────────────────────────────────────────
@login_required
@role_required(['admin'])
def admin_statistiques(request):
    active_tab = request.GET.get('tab', 'global')
    if active_tab not in ('global', 'encadrants', 'entreprises', 'resultats'):
        active_tab = 'global'

    ctx = {'active_tab': active_tab, 'filieres': FILIERES}
    ctx.update(_compute_global())
    ctx.update(_compute_encadrants())
    ctx.update(_compute_entreprises())
    ctx.update(_compute_resultats())

    return render(request, 'core/admin_statistiques.html', ctx)
