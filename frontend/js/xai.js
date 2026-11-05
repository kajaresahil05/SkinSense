// Explainable AI (XAI) Helper Module
document.addEventListener('DOMContentLoaded', () => {
    initXAIModule();
});

function initXAIModule() {
    const slider = document.getElementById('xai-opacity-slider');

    // Interactive Opacity Control Slider
    if (slider) {
        slider.addEventListener('input', (e) => {
            const opacityVal = e.target.value;
            const opacityValBadge = document.getElementById('xai-opacity-val');
            const imgHeatmap = document.getElementById('xai-img-heatmap');
            
            if (opacityValBadge) opacityValBadge.textContent = `${opacityVal}%`;
            if (imgHeatmap) imgHeatmap.style.opacity = (opacityVal / 100).toString();
        });
    }
}

function setHeatmapOpacity(percentage) {
    const slider = document.getElementById('xai-opacity-slider');
    const imgHeatmap = document.getElementById('xai-img-heatmap');
    const opacityValBadge = document.getElementById('xai-opacity-val');

    if (slider) slider.value = percentage;
    if (opacityValBadge) opacityValBadge.textContent = `${percentage}%`;
    if (imgHeatmap) imgHeatmap.style.opacity = (percentage / 100).toString();
}
