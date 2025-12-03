// AI Cover Generator - JavaScript

// State
let currentStep = 1;
let selectedSize = null;
let selectedStyle = null;
let currentTaskId = null;

// DOM Elements
const steps = document.querySelectorAll('.step');
const stepContents = document.querySelectorAll('.step-content');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const generateBtn = document.getElementById('generate-btn');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeSizeCards();
    initializeStyleCards();
    initializeCategorySelect();
    loadTemplates();
});

// Initialize size card selection
function initializeSizeCards() {
    const sizeCards = document.querySelectorAll('.size-card');
    sizeCards.forEach(card => {
        card.addEventListener('click', () => {
            sizeCards.forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedSize = card.dataset.size;
            updateNextButton();
            updateSummary();
        });
    });
}

// Initialize style card selection
function initializeStyleCards() {
    const styleCards = document.querySelectorAll('.style-card');
    styleCards.forEach(card => {
        card.addEventListener('click', () => {
            styleCards.forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedStyle = card.dataset.style;
            updateNextButton();
            updateSummary();
        });
    });
}

// Initialize category select for suggestions
function initializeCategorySelect() {
    const categorySelect = document.getElementById('category-select');
    categorySelect.addEventListener('change', async () => {
        const category = categorySelect.value;
        if (category) {
            await loadSuggestions(category);
        }
    });
}

// Load suggestions from API
async function loadSuggestions(category) {
    try {
        const response = await fetch('/covers/api/suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                size: selectedSize, 
                style: selectedStyle,
                category: category
            })
        });
        
        const data = await response.json();
        if (data.success) {
            displaySuggestions(data.suggestions);
        }
    } catch (error) {
        console.error('Error loading suggestions:', error);
    }
}

// Display suggestions
function displaySuggestions(suggestions) {
    const suggestionsBox = document.getElementById('suggestions-box');
    const suggestionsList = document.getElementById('suggestions-list');
    
    suggestionsBox.style.display = 'block';
    suggestionsList.innerHTML = '';
    
    suggestions.forEach(suggestion => {
        const chip = document.createElement('span');
        chip.className = 'suggestion-chip';
        chip.textContent = suggestion;
        chip.addEventListener('click', () => {
            const promptTextarea = document.getElementById('user-prompt');
            promptTextarea.value = suggestion;
        });
        suggestionsList.appendChild(chip);
    });
}

// Load templates
async function loadTemplates() {
    try {
        const response = await fetch('/covers/api/templates');
        const data = await response.json();
        
        if (data.success) {
            displayTemplates(data.templates);
        }
    } catch (error) {
        console.error('Error loading templates:', error);
    }
}

// Display templates
function displayTemplates(templates) {
    const grid = document.getElementById('templates-grid');
    grid.innerHTML = '';
    
    templates.forEach(template => {
        const card = document.createElement('div');
        card.className = 'template-card';
        card.innerHTML = `
            <div class="template-preview" style="background: ${template.preview_color}">
                🎨
            </div>
            <h4>${template.name}</h4>
            <p>${template.prompt.substring(0, 50)}...</p>
        `;
        
        card.addEventListener('click', () => {
            // Select size
            const sizeCard = document.querySelector(`[data-size="${template.size}"]`);
            if (sizeCard) {
                document.querySelectorAll('.size-card').forEach(c => c.classList.remove('selected'));
                sizeCard.classList.add('selected');
                selectedSize = template.size;
            }
            
            // Select style
            const styleCard = document.querySelector(`[data-style="${template.style}"]`);
            if (styleCard) {
                document.querySelectorAll('.style-card').forEach(c => c.classList.remove('selected'));
                styleCard.classList.add('selected');
                selectedStyle = template.style;
            }
            
            // Set prompt
            document.getElementById('user-prompt').value = template.prompt;
            
            // Update and go to step 3
            updateNextButton();
            updateSummary();
            goToStep(3);
        });
        
        grid.appendChild(card);
    });
}

// Update next button state
function updateNextButton() {
    switch(currentStep) {
        case 1:
            nextBtn.disabled = !selectedSize;
            break;
        case 2:
            nextBtn.disabled = !selectedStyle;
            break;
        case 3:
            nextBtn.disabled = false;
            break;
    }
}

// Update summary
function updateSummary() {
    // Platform/Size
    if (selectedSize) {
        const sizeCard = document.querySelector(`[data-size="${selectedSize}"]`);
        if (sizeCard) {
            const sizeName = sizeCard.querySelector('h4').textContent;
            const sizeDimensions = sizeCard.querySelector('.size-dimensions').textContent;
            document.getElementById('summary-platform').textContent = `${sizeName} (${sizeDimensions})`;
        }
    }
    
    // Style
    if (selectedStyle) {
        const styleCard = document.querySelector(`[data-style="${selectedStyle}"]`);
        if (styleCard) {
            const styleName = styleCard.querySelector('h4').textContent;
            document.getElementById('summary-style').textContent = styleName;
        }
    }
}

// Navigation
function nextStep() {
    if (currentStep < 4) {
        goToStep(currentStep + 1);
    }
}

function prevStep() {
    if (currentStep > 1) {
        goToStep(currentStep - 1);
    }
}

function goToStep(step) {
    currentStep = step;
    
    // Update step indicators
    steps.forEach((s, index) => {
        s.classList.remove('active', 'completed');
        if (index + 1 < step) {
            s.classList.add('completed');
        } else if (index + 1 === step) {
            s.classList.add('active');
        }
    });
    
    // Update step content
    stepContents.forEach((content, index) => {
        content.classList.remove('active');
        if (index + 1 === step) {
            content.classList.add('active');
        }
    });
    
    // Update buttons
    prevBtn.style.display = step > 1 && step < 4 ? 'inline-flex' : 'none';
    nextBtn.style.display = step < 3 ? 'inline-flex' : 'none';
    generateBtn.style.display = step === 3 ? 'inline-flex' : 'none';
    
    updateNextButton();
}

// Generate cover
async function generateCover() {
    const customText = document.getElementById('custom-text').value;
    const userPrompt = document.getElementById('user-prompt').value;
    
    // Go to result step
    goToStep(4);
    
    // Show loading
    document.getElementById('loading-state').style.display = 'block';
    document.getElementById('result-image').style.display = 'none';
    document.getElementById('result-actions').style.display = 'none';
    document.getElementById('error-state').style.display = 'none';
    
    try {
        const response = await fetch('/covers/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                size: selectedSize,
                style: selectedStyle,
                text: customText,
                prompt: userPrompt
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentTaskId = data.taskId;
            checkStatus();
        } else {
            showError(data.error || 'Failed to start generation');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}

// Check generation status
async function checkStatus() {
    if (!currentTaskId) return;
    
    try {
        const response = await fetch(`/covers/api/status/${currentTaskId}`);
        const data = await response.json();
        
        if (data.state === 'completed' && data.imageUrl) {
            showResult(data.imageUrl);
        } else if (data.state === 'failed') {
            showError(data.error || 'Generation failed');
        } else {
            // Still processing, check again in 2 seconds
            setTimeout(checkStatus, 2000);
        }
    } catch (error) {
        showError('Error checking status: ' + error.message);
    }
}

// Show result
function showResult(imageUrl) {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('result-image').style.display = 'block';
    document.getElementById('result-actions').style.display = 'flex';
    
    const img = document.getElementById('generated-image');
    img.src = imageUrl;
    
    const downloadBtn = document.getElementById('download-btn');
    downloadBtn.href = imageUrl;
    downloadBtn.download = `cover_${selectedSize}_${Date.now()}.png`;
}

// Show error
function showError(message) {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('error-state').style.display = 'block';
    document.getElementById('error-message').textContent = message;
}

// Regenerate
function regenerate() {
    generateCover();
}

// Start over
function startOver() {
    selectedSize = null;
    selectedStyle = null;
    currentTaskId = null;
    
    document.querySelectorAll('.size-card').forEach(c => c.classList.remove('selected'));
    document.querySelectorAll('.style-card').forEach(c => c.classList.remove('selected'));
    document.getElementById('custom-text').value = '';
    document.getElementById('user-prompt').value = '';
    document.getElementById('category-select').value = '';
    document.getElementById('suggestions-box').style.display = 'none';
    
    goToStep(1);
}

