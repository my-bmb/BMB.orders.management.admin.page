// static/js/admin.js
// Additional JavaScript functions

// Auto-refresh dashboard every 60 seconds
function autoRefreshDashboard() {
    if (window.location.pathname === '/admin/dashboard') {
        setTimeout(() => {
            window.location.reload();
        }, 60000); // 60 seconds
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl + S for search
    if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        document.getElementById('searchInput').focus();
    }
    
    // Ctrl + D for dashboard
    if (e.ctrlKey && e.key === 'd') {
        e.preventDefault();
        window.location.href = '/admin/dashboard';
    }
    
    // Ctrl + O for orders
    if (e.ctrlKey && e.key === 'o') {
        e.preventDefault();
        window.location.href = '/admin/orders';
    }
    
    // Ctrl + C for customers
    if (e.ctrlKey && e.key === 'c') {
        e.preventDefault();
        window.location.href = '/admin/customers';
    }
    
    // Esc to close modals
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal.show');
        modals.forEach(modal => {
            bootstrap.Modal.getInstance(modal).hide();
        });
    }
});

// Format numbers with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Format date to readable string
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Copy to clipboard function
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard: ' + text);
    }).catch(err => {
        console.error('Failed to copy: ', err);
    });
}

// Export functions
function exportTableToCSV(tableId, filename) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    let csv = [];
    const rows = table.querySelectorAll('tr');
    
    for (let i = 0; i < rows.length; i++) {
        let row = [], cols = rows[i].querySelectorAll('td, th');
        
        for (let j = 0; j < cols.length; j++) {
            let data = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, '').replace(/(\s\s)/gm, ' ');
            data = data.replace(/"/g, '""');
            row.push('"' + data + '"');
        }
        
        csv.push(row.join(','));
    }
    
    // Download CSV file
    const csvFile = new Blob([csv.join('\n')], { type: 'text/csv' });
    const downloadLink = document.createElement('a');
    
    downloadLink.download = filename;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Auto-refresh dashboard
    autoRefreshDashboard();
    
    // Add tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Add confirmation for delete actions
    const deleteButtons = document.querySelectorAll('.btn-delete');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this item?')) {
                e.preventDefault();
            }
        });
    });
    
    // Auto-submit forms when filters change
    const autoSubmitForms = document.querySelectorAll('form[data-auto-submit]');
    autoSubmitForms.forEach(form => {
        const inputs = form.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('change', function() {
                form.submit();
            });
        });
    });
});

// Theme switcher (light/dark mode)
function toggleTheme() {
    const body = document.body;
    const currentTheme = body.getAttribute('data-bs-theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    body.setAttribute('data-bs-theme', newTheme);
    localStorage.setItem('adminTheme', newTheme);
    
    // Update theme icon
    const themeIcon = document.getElementById('themeIcon');
    if (themeIcon) {
        themeIcon.className = newTheme === 'dark' ? 'bi bi-sun' : 'bi bi-moon';
    }
}

// Load saved theme
document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('adminTheme') || 'light';
    document.body.setAttribute('data-bs-theme', savedTheme);
    
    // Add theme toggle button if not exists
    if (!document.getElementById('themeToggle')) {
        const themeToggle = document.createElement('button');
        themeToggle.id = 'themeToggle';
        themeToggle.className = 'btn btn-outline-secondary btn-sm ms-2';
        themeToggle.innerHTML = '<i id="themeIcon" class="bi ' + (savedTheme === 'dark' ? 'bi-sun' : 'bi-moon') + '"></i>';
        themeToggle.onclick = toggleTheme;
        
        const navbar = document.querySelector('.navbar .ms-auto');
        if (navbar) {
            navbar.appendChild(themeToggle);
        }
    }
});