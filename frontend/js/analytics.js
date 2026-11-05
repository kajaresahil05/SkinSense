// Developer & Admin Model Analytics Dashboard Module
document.addEventListener('DOMContentLoaded', () => {
    initAnalytics();
});

let classChart = null;
let distChart = null;

function initAnalytics() {
    const adminModal = document.getElementById('adminAnalyticsModal');
    if (adminModal) {
        adminModal.addEventListener('shown.bs.modal', () => loadAnalyticsData());
    }
}

async function loadAnalyticsData() {
    try {
        const res = await fetch('/api/analytics');
        const data = await res.json();

        if (data.status === 'success') {
            if (data.benchmark_metrics) {
                renderKPIs(data.benchmark_metrics.overall_metrics);
                renderClassPerformanceChart(data.benchmark_metrics.per_class_metrics);
                renderLiveDistributionChart(data.live_distribution, data.benchmark_metrics.per_class_metrics);
            }
            if (data.xai_metrics) {
                renderXAIAnalytics(data.xai_metrics);
            }
        }
    } catch (err) {
        console.error("Failed to load analytics data:", err);
    }
}

function renderXAIAnalytics(xai) {
    if (!xai) return;
    const totalEl = document.getElementById('xai-analytics-total');
    const rateEl = document.getElementById('xai-analytics-success-rate');

    if (totalEl) totalEl.textContent = xai.total_assessments_logged || 0;
    
    if (rateEl) {
        const total = xai.total_assessments_logged || 0;
        const success = xai.successful_explanations || 0;
        const rate = total > 0 ? ((success / total) * 100).toFixed(1) : 100;
        rateEl.textContent = `${rate}%`;
    }
}

function renderKPIs(overall) {
    if (!overall) return;
    const acc = document.getElementById('kpi-accuracy');
    const prec = document.getElementById('kpi-precision');
    const rec = document.getElementById('kpi-recall');
    const f1 = document.getElementById('kpi-f1');

    if (acc) acc.textContent = `${(overall.accuracy * 100).toFixed(2)}%`;
    if (prec) prec.textContent = overall.precision.toFixed(4);
    if (rec) rec.textContent = overall.recall.toFixed(4);
    if (f1) f1.textContent = overall.f1_score.toFixed(4);
}

function renderClassPerformanceChart(perClassData) {
    const canvas = document.getElementById('chart-class-performance');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (classChart) {
        classChart.destroy();
        classChart = null;
    }

    const labels = perClassData.map(d => d.name);
    const precisions = perClassData.map(d => d.precision);
    const recalls = perClassData.map(d => d.recall);
    const f1s = perClassData.map(d => d.f1_score);

    classChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Precision',
                    data: precisions,
                    backgroundColor: 'rgba(13, 148, 136, 0.8)',
                    borderColor: '#0d9488',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    barPercentage: 0.8,
                    categoryPercentage: 0.75
                },
                {
                    label: 'Recall',
                    data: recalls,
                    backgroundColor: 'rgba(2, 132, 199, 0.8)',
                    borderColor: '#0284c7',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    barPercentage: 0.8,
                    categoryPercentage: 0.75
                },
                {
                    label: 'F1-Score',
                    data: f1s,
                    backgroundColor: 'rgba(16, 185, 129, 0.8)',
                    borderColor: '#10b981',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    barPercentage: 0.8,
                    categoryPercentage: 0.75
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    min: 0,
                    max: 1.0,
                    grid: { color: 'rgba(0, 0, 0, 0.05)' },
                    ticks: { color: '#64748b' }
                },
                x: {
                    grid: { color: 'rgba(0, 0, 0, 0.02)' },
                    ticks: { color: '#334155', maxRotation: 35 }
                }
            },
            plugins: {
                legend: { position: 'top' }
            }
        }
    });
}

function renderLiveDistributionChart(liveDist, perClassData) {
    const canvas = document.getElementById('chart-live-distribution');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (distChart) {
        distChart.destroy();
        distChart = null;
    }

    let labels = [];
    let counts = [];

    if (liveDist && liveDist.length > 0) {
        labels = liveDist.map(d => d.predicted_name);
        counts = liveDist.map(d => d.count);
    } else {
        labels = perClassData ? perClassData.map(d => d.name) : [];
        counts = perClassData ? perClassData.map(d => d.support) : [];
    }

    const colors = [
        '#0d9488', '#0284c7', '#10b981', '#d97706',
        '#e11d48', '#8b5cf6', '#ec4899', '#3b82f6', '#14b8a6'
    ];

    distChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: colors.slice(0, labels.length),
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });
}
