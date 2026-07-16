// ==========================================
// AI Sales OS - Frontend Logic (script.js)
// ==========================================

// Global App State
let customers = [];
let selectedCustomerId = null;
let currentFilter = 'all';
let currentChannelFilter = 'all';
let searchQuery = '';

// DOM Elements
const conversationsContainer = document.getElementById('conversations-container');
const chatMessagesContainer = document.getElementById('chat-messages-container');
const chatInput = document.getElementById('chat-input');
const chatForm = document.getElementById('chat-form');
const typingIndicator = document.getElementById('typing-indicator');
const sidebarUnreadCount = document.getElementById('sidebar-unread-count');

// Detail Panel Elements
const detailsAvatarLetter = document.getElementById('details-avatar-letter');
const detailsName = document.getElementById('details-name');
const detailsCompany = document.getElementById('details-company');
const detailsStatus = document.getElementById('details-status');
const detailsScore = document.getElementById('details-score');
const detailsPhone = document.getElementById('details-phone');
const detailsEmail = document.getElementById('details-email');
const detailsCity = document.getElementById('details-city');
const detailsPlatform = document.getElementById('details-platform');
const detailsProduct = document.getElementById('details-product');
const detailsQuantity = document.getElementById('details-quantity');
const detailsBudget = document.getElementById('details-budget');
const detailsSummary = document.getElementById('details-summary');
const detailsNotes = document.getElementById('details-notes');

// Controls
const simulationModeCheckbox = document.getElementById('simulation-mode-checkbox');
const modeDescText = document.getElementById('mode-desc-text');
const aiStatusLabel = document.getElementById('ai-status-label');
const aiStatusIndicator = document.querySelector('.ai-status .status-indicator');
const pageTitle = document.getElementById('page-title');

// Search & Filters
const convSearch = document.getElementById('conv-search');
const globalSearch = document.getElementById('global-search');
const filterButtons = document.querySelectorAll('.filter-btn');

// Startup & Initialization
window.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupEventListeners();
});

function initApp() {
    fetchCustomers(true); // Load customers and auto-select the first one
    connectAdminWebSocket();
}

let adminWs = null;
function connectAdminWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    adminWs = new WebSocket(`${protocol}//${window.location.host}/ws/dashboard`);
    
    adminWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'new_message') {
            // If the message belongs to the currently selected customer, append it
            if (selectedCustomerId == data.customer_id) {
                appendMessage(data.message, false);
            }
            // Update customer list to reflect unread status
            fetchCustomers(false);
        }
    };
}

function setupEventListeners() {
    // Chat Form Submit (Send Message)
    chatForm.addEventListener('submit', handleSendMessage);

    // Simulation Mode Checkbox Toggle
    simulationModeCheckbox.addEventListener('change', handleModeToggle);

    // Search Box (Inbox Left Panel)
    convSearch.addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase();
        renderConversationsList();
    });

    // Global Search (Top Navbar)
    globalSearch.addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase();
        convSearch.value = e.target.value; // Sync with left panel search
        renderConversationsList();
    });

    // Filter Buttons
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            renderConversationsList();
        });
    });

    // Channel Filters (Sidebar)
    const channelItems = document.querySelectorAll('.channel-item');
    channelItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            channelItems.forEach(i => i.classList.remove('active-channel'));
            item.classList.add('active-channel');
            currentChannelFilter = item.dataset.channel;
            
            // Auto close mobile sidebar
            document.querySelector('.sidebar').classList.remove('active');
            
            renderConversationsList();
        });
    });

    // Internal Notes Auto-save on blur
    detailsNotes.addEventListener('blur', saveInternalNotes);

    // Delete Customer Profile Button
    document.getElementById('action-delete-customer').addEventListener('click', handleDeleteCustomer);

    // Quick Action button demo alerts
    document.getElementById('action-catalogue').addEventListener('click', () => showToast("Catalogue shared with customer"));
    document.getElementById('action-quotation').addEventListener('click', () => showToast("Quotation sent to email"));
    
    // Follow-up Feature
    const followupModal = document.getElementById('followup-modal');
    const followupCloseBtn = document.getElementById('followup-modal-close');
    const sendFollowupBtn = document.getElementById('send-followup-btn');
    const followupMessageText = document.getElementById('followup-message-text');

    document.getElementById('action-followup').addEventListener('click', () => {
        if (!selectedCustomerId) {
            showToast("Please select a customer first", "error");
            return;
        }
        const cust = customers.find(c => c.id === selectedCustomerId);
        if (!cust) return;

        // Generate smart default text
        const name = cust.name ? cust.name.split(' ')[0] : 'there';
        const product = cust.interested_product || 'our services';
        
        followupMessageText.value = `Hi ${name},\n\nI'm following up to see if you are still interested in ${product}? Please let me know if you have any questions or need further assistance!\n\nBest,\nSarah Connor`;
        
        followupModal.style.display = 'flex';
    });

    followupCloseBtn.addEventListener('click', () => {
        followupModal.style.display = 'none';
    });

    sendFollowupBtn.addEventListener('click', async () => {
        const text = followupMessageText.value.trim();
        if (!text || !selectedCustomerId) return;
        
        sendFollowupBtn.disabled = true;
        sendFollowupBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sending...';

        const isoTime = new Date().toISOString();

        try {
            const response = await fetch('/messages', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    customer_id: selectedCustomerId,
                    sender: 'human',
                    text: text,
                    timestamp: isoTime,
                    simulation_mode: false
                })
            });
            
            if (!response.ok) throw new Error("Failed to send follow-up message");
            
            // Re-fetch to update view instantly
            await fetchMessages(selectedCustomerId);
            await fetchCustomers(false);
            
            followupModal.style.display = 'none';
            showToast("Follow-up message sent successfully!");
        } catch (error) {
            console.error(error);
            showToast("Error sending follow-up message", "error");
        } finally {
            sendFollowupBtn.disabled = false;
            sendFollowupBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Send Message';
        }
    });
    document.getElementById('action-assign').addEventListener('click', () => showToast("Sales Executive assigned to lead"));
}

// ==========================================
// API CALLS
// ==========================================

// Fetch all customers from FastAPI
async function fetchCustomers(autoSelectFirst = false) {
    try {
        const response = await fetch('/customers');
        if (!response.ok) throw new Error("Failed to fetch customers");
        customers = await response.json();
        
        updateSidebarUnreadCount();
        renderConversationsList();

        if (autoSelectFirst && customers.length > 0) {
            selectCustomer(customers[0].id);
        } else if (selectedCustomerId) {
            // Refresh details of the currently selected customer
            const activeCust = customers.find(c => c.id === selectedCustomerId);
            if (activeCust) {
                updateRightPanel(activeCust);
            } else {
                // The active customer was probably deleted. Select the first remaining one
                if (customers.length > 0) {
                    selectCustomer(customers[0].id);
                } else {
                    clearChatUI();
                }
            }
        } else if (customers.length === 0) {
            clearChatUI();
        }
    } catch (error) {
        console.error(error);
        showToast("Error loading conversations", "error");
    }
}

// Fetch messages for a customer
async function fetchMessages(customerId) {
    try {
        const response = await fetch(`/messages/${customerId}`);
        if (!response.ok) throw new Error("Failed to fetch messages");
        const messages = await response.json();
        renderMessages(messages);
    } catch (error) {
        console.error(error);
        showToast("Error loading messages", "error");
    }
}

// Select and load a customer
function selectCustomer(customerId) {
    selectedCustomerId = customerId;
    
    // Find active customer object
    const customer = customers.find(c => c.id === customerId);
    if (!customer) return;

    // Highlight card
    const cards = document.querySelectorAll('.conv-card');
    cards.forEach(card => {
        card.classList.remove('active');
        if (parseInt(card.dataset.id) === customerId) {
            card.classList.add('active');
            
            // Clear unread badge locally
            if (card.classList.contains('unread')) {
                card.classList.remove('unread');
                customer.unread = false;
                updateSidebarUnreadCount();
            }
        }
    });

    // Update Headers
    document.getElementById('chat-customer-title').innerText = customer.name;
    document.getElementById('chat-customer-subtitle').innerText = customer.company || "Independent Buyer";

    // Set simulator mode checkbox based on whether it is managed by AI or human
    simulationModeCheckbox.checked = customer.is_ai_managed;
    setModeUI(customer.is_ai_managed);

    // Populate Sidebar Details Panel
    updateRightPanel(customer);

    // Fetch and display messages
    fetchMessages(customerId);
}

// Post a new message
async function handleSendMessage(e) {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text || !selectedCustomerId) return;

    chatInput.value = '';

    // Determine sender based on switch mode
    const isSimMode = simulationModeCheckbox.checked;
    const sender = isSimMode ? 'customer' : 'human';

    // Format time
    const timeNow = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const isoTime = new Date().toISOString();

    // Append message locally first for instant feedback
    appendMessage({
        sender: sender,
        text: text,
        timestamp: isoTime
    });
    
    // Find conversation ID
    const cust = customers.find(c => c.id === selectedCustomerId);
    if (!cust) return;
    
    try {
        const response = await fetch('/messages', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                customer_id: selectedCustomerId,
                sender: sender,
                text: text,
                timestamp: isoTime,
                simulation_mode: isSimMode
            })
        });
        
        if (!response.ok) throw new Error("Failed to send message");
        const result = await response.json();

        // Refresh customers list to capture updated status details
        await fetchCustomers(false);

        // If AI replied
        if (isSimMode && result.ai_reply) {
            setTimeout(() => {
                showTypingIndicator(false);
                appendMessage(result.ai_reply);
                scrollChatToBottom();
                showToast(`AI reply received`);
                
                // Refresh list and detail view to capture the updated fields
                fetchCustomers(false);
            }, 1000);
        } else {
            showTypingIndicator(false);
        }

    } catch (error) {
        console.error(error);
        showTypingIndicator(false);
        showToast("Error sending message", "error");
    }
}

// Save notes to backend
async function saveInternalNotes() {
    if (!selectedCustomerId) return;
    const notesText = detailsNotes.value;
    
    try {
        const response = await fetch(`/customers/${selectedCustomerId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ internal_notes: notesText })
        });
        
        if (!response.ok) throw new Error("Failed to save notes");
        showToast("Notes saved successfully");
        
        // Refresh local cache
        const customer = customers.find(c => c.id === selectedCustomerId);
        if (customer) customer.internal_notes = notesText;

    } catch (error) {
        console.error(error);
        showToast("Failed to save notes", "error");
    }
}

// Delete a customer profile
async function handleDeleteCustomer() {
    if (!selectedCustomerId) return;
    
    const customer = customers.find(c => c.id === selectedCustomerId);
    const customerName = customer ? customer.name : "this customer";
    
    if (!confirm(`Are you sure you want to permanently delete the profile for ${customerName}? All matching messages and conversation history will be lost.`)) {
        return;
    }

    try {
        const response = await fetch(`/customers/${selectedCustomerId}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error("Failed to delete customer");
        
        showToast("Customer profile deleted successfully");
        selectedCustomerId = null;
        
        // Fetch remaining list
        fetchCustomers(true);

    } catch (error) {
        console.error(error);
        showToast("Failed to delete customer", "error");
    }
}

// ==========================================
// RENDER METHODS
// ==========================================

// Populate conversations panel
function renderConversationsList() {
    conversationsContainer.innerHTML = '';

    // Apply Filter and Search
    const filtered = customers.filter(cust => {
        const matchesSearch = cust.name.toLowerCase().includes(searchQuery) ||
                             (cust.company && cust.company.toLowerCase().includes(searchQuery)) ||
                             (cust.last_message_text && cust.last_message_text.toLowerCase().includes(searchQuery));
        
        if (!matchesSearch) return false;

        // Channel Filter
        if (currentChannelFilter !== 'all' && cust.channel !== currentChannelFilter) {
            return false;
        }

        // Filters: All, Unread, Hot, Warm, Cold, AI, Human
        if (currentFilter === 'unread') return cust.unread;
        if (currentFilter === 'hot') return cust.lead_status.toLowerCase() === 'hot';
        if (currentFilter === 'warm') return cust.lead_status.toLowerCase() === 'warm';
        if (currentFilter === 'cold') return cust.lead_status.toLowerCase() === 'cold';
        if (currentFilter === 'ai') return cust.is_ai_managed;
        if (currentFilter === 'human') return !cust.is_ai_managed;

        return true;
    });

    if (filtered.length === 0) {
        conversationsContainer.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-folder-open" style="font-size: 1.5rem;"></i>
                <span>No conversations found</span>
            </div>
        `;
        return;
    }

    filtered.forEach(cust => {
        let platformIcon = '<i class="fa-solid fa-comments text-website"></i>';
        if (cust.channel === 'WhatsApp') {
            platformIcon = '<i class="fa-brands fa-whatsapp text-whatsapp"></i>';
        } else if (cust.channel === 'Instagram') {
            platformIcon = '<i class="fa-brands fa-instagram text-instagram"></i>';
        } else if (cust.channel === 'Email') {
            platformIcon = '<i class="fa-solid fa-envelope text-email"></i>';
        }

        const statusClass = cust.lead_status.toLowerCase(); // maps to hot, warm, cold, new, etc.

        const card = document.createElement('div');
        card.className = `conv-card ${cust.unread ? 'unread' : ''} ${selectedCustomerId === cust.id ? 'active' : ''}`;
        card.dataset.id = cust.id;
        card.innerHTML = `
            <div class="conv-avatar-container">
                <div class="conv-avatar">${cust.name.charAt(0)}</div>
                <div class="platform-badge">${platformIcon}</div>
            </div>
            <div class="conv-content">
                <div class="conv-header">
                    <span class="conv-name">${cust.name}</span>
                    <span class="conv-time">${cust.last_message_time || ''}</span>
                </div>
                <div class="conv-company">${cust.company || 'New Lead'}</div>
                <div class="conv-msg-preview">${cust.last_message_text || 'No messages yet'}</div>
                <div class="conv-footer">
                    <span class="conv-status-badge ${statusClass}">${cust.lead_status}</span>
                    ${cust.unread ? '<div class="conv-unread-dot"></div>' : ''}
                </div>
            </div>
        `;

        card.addEventListener('click', () => selectCustomer(cust.id));
        conversationsContainer.appendChild(card);
    });
}

// Populate messages inside chat logs
function renderMessages(messagesList) {
    chatMessagesContainer.innerHTML = '';
    
    if (messagesList.length === 0) {
        chatMessagesContainer.innerHTML = `
            <div class="empty-state">
                <span>Start conversation by typing below.</span>
            </div>
        `;
        return;
    }

    messagesList.forEach(msg => {
        appendMessage(msg);
    });

    scrollChatToBottom();
}

// Append a message bubble to Chat View
function appendMessage(msg) {
    const wrapper = document.createElement('div');
    const isLeft = msg.sender === 'customer';
    wrapper.className = `msg-wrapper ${isLeft ? 'left' : 'right'} ${msg.sender === 'ai' ? 'ai-msg' : 'human-msg'}`;

    let tag = '';
    if (msg.sender === 'ai') tag = '<span class="sender-tag ai-tag"><i class="fa-solid fa-wand-magic-sparkles"></i> AI</span>';
    else if (msg.sender === 'human') tag = '<span class="sender-tag human-tag">Agent</span>';
    else tag = '<span class="sender-tag customer-tag">Customer</span>';

    wrapper.innerHTML = `
        <div class="msg-bubble">${msg.text}</div>
        <div class="msg-info">
            ${isLeft ? tag : ''}
            <span class="msg-time">${msg.timestamp}</span>
            ${!isLeft ? tag : ''}
        </div>
    `;

    chatMessagesContainer.appendChild(wrapper);
}

// Update Details panel
function updateRightPanel(customer) {
    detailsAvatarLetter.innerText = customer.name.charAt(0);
    detailsName.innerText = customer.name;
    detailsCompany.innerText = customer.company || "Independent Buyer";
    detailsNotes.value = customer.internal_notes || '';

    const statusClass = customer.lead_status.toLowerCase();
    
    detailsStatus.innerText = customer.lead_status;
    detailsStatus.className = `badge-status ${statusClass}`;
    detailsScore.innerText = `Score: ${customer.lead_score}`;

    detailsPhone.innerText = customer.phone || 'Not provided';
    detailsEmail.innerText = customer.email || '-';
    detailsCity.innerText = customer.city || '-';
    detailsPlatform.innerText = customer.channel || 'Website Chat';
    
    detailsProduct.innerText = customer.interested_product || 'Not provided';
    detailsQuantity.innerText = customer.quantity || 'Not provided';
    detailsBudget.innerText = customer.budget ? `$${customer.budget.toLocaleString(undefined, {minimumFractionDigits: 2})}` : 'Not provided';
    
    if (customer.ai_summary) {
        detailsSummary.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles text-spark"></i> ${customer.ai_summary}`;
    } else {
        detailsSummary.innerText = "Awaiting customer profile details to generate AI summary.";
    }
}

// Reset UI state when empty
function clearChatUI() {
    document.getElementById('chat-customer-title').innerText = 'Select a conversation';
    document.getElementById('chat-customer-subtitle').innerText = 'Choose a lead from the inbox to reply';
    chatMessagesContainer.innerHTML = `
        <div class="empty-state">
            <i class="fa-solid fa-comments" style="font-size: 2.5rem; opacity: 0.3;"></i>
            <span>No conversation selected</span>
        </div>
    `;
    
    detailsAvatarLetter.innerText = '-';
    detailsName.innerText = 'No Lead Selected';
    detailsCompany.innerText = 'Please select a conversation';
    detailsStatus.innerText = 'Offline';
    detailsStatus.className = 'badge-status';
    detailsScore.innerText = 'Score: 0';
    
    detailsPhone.innerText = '-';
    detailsEmail.innerText = '-';
    detailsCity.innerText = '-';
    detailsPlatform.innerText = '-';
    detailsProduct.innerText = '-';
    detailsQuantity.innerText = '-';
    detailsBudget.innerText = '-';
    detailsSummary.innerText = 'Select a lead to see AI summary.';
    detailsNotes.value = '';
}

// ==========================================
// HELPERS & INTERACTIVE EFFECTS
// ==========================================

function handleModeToggle(e) {
    const isSimMode = e.target.checked;
    setModeUI(isSimMode);
    
    // Save AI/Human status toggle state in backend database
    if (selectedCustomerId) {
        fetch(`/customers/${selectedCustomerId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_ai_managed: isSimMode })
        })
        .then(res => {
            if (res.ok) {
                // Refresh local model
                const customer = customers.find(c => c.id === selectedCustomerId);
                if (customer) customer.is_ai_managed = isSimMode;
                renderConversationsList();
            }
        });
    }
}

function setModeUI(isSimMode) {
    if (isSimMode) {
        modeDescText.innerText = "Test AI";
        modeDescText.style.color = 'var(--color-primary)';
        aiStatusLabel.innerText = "AI Agent: Active";
        aiStatusIndicator.className = "status-indicator active";
        chatInput.placeholder = "Type a message to simulate customer...";
    } else {
        modeDescText.innerText = "Manual";
        modeDescText.style.color = 'var(--text-muted)';
        aiStatusLabel.innerText = "AI Agent: Paused";
        aiStatusIndicator.className = "status-indicator paused";
        chatInput.placeholder = "Type a message as Sarah Connor (Sales Lead)...";
    }
}

function updateSidebarUnreadCount() {
    const count = customers.filter(c => c.unread).length;
    sidebarUnreadCount.innerText = count;
    sidebarUnreadCount.style.display = count > 0 ? 'inline-block' : 'none';
}

function showTypingIndicator(show) {
    typingIndicator.style.display = show ? 'flex' : 'none';
    if (show) scrollChatToBottom();
}

function scrollChatToBottom() {
    chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
}

// Toast Popup
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = '<i class="fa-solid fa-check-circle text-success"></i>';
    if (type === 'error') {
        icon = '<i class="fa-solid fa-exclamation-circle text-danger"></i>';
    }
    
    toast.innerHTML = `
        ${icon}
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fade-out');
        toast.addEventListener('animationend', () => toast.remove());
    }, 3000);
}

/* ==========================================
   V3: ADMIN & SETTINGS LOGIC
   ========================================== */

let currentAdmin = null;
let currentSettings = null;

// Auth check on load
async function checkAuth() {
    try {
        const res = await fetch('/admin/profile');
        if (!res.ok) {
            window.location.href = '/login.html';
            return false;
        }
        currentAdmin = await res.json();
        
        // Update Navbar Profile
        document.getElementById('navbar-username').textContent = currentAdmin.name;
        document.getElementById('navbar-role').textContent = currentAdmin.role;
        
        if (currentAdmin.profile_photo) {
            document.getElementById('navbar-avatar').src = currentAdmin.profile_photo;
            document.getElementById('profile-modal-avatar-initial').style.display = 'none';
            const modalImg = document.getElementById('profile-modal-avatar-img');
            if(modalImg) {
                modalImg.src = currentAdmin.profile_photo;
                modalImg.style.display = 'block';
            }
        } else {
            document.getElementById('profile-modal-avatar-initial').textContent = currentAdmin.name.charAt(0).toUpperCase();
        }
        
        // Try fetching branding settings globally if not in currentAdmin
        fetchGlobalBranding();
        
        return true;
    } catch(e) {
        window.location.href = '/login.html';
        return false;
    }
}

// Fetch Global Branding
async function fetchGlobalBranding() {
    try {
        const res = await fetch('/api/branding');
        if (res.ok) {
            const data = await res.json();
            updateGlobalBranding(data.company_name, data.business_logo);
        }
    } catch (e) {
        console.error("Could not load global branding", e);
    }
}

function updateGlobalBranding(name, logo) {
    const logoTexts = document.querySelectorAll('.logo-text');
    logoTexts.forEach(el => el.textContent = name || "AI Sales OS");
    
    // If we have a logo icon somewhere, update it
    const logoIcons = document.querySelectorAll('.logo-icon');
    if (logo) {
        logoIcons.forEach(el => {
            el.innerHTML = `<img src="${logo}" style="width: 24px; height: 24px; object-fit: contain;">`;
        });
    }
}
const originalInitApp = initApp;
initApp = async function() {
    const isAuthenticated = await checkAuth();
    if (isAuthenticated) {
        originalInitApp();
    }
};

// Replace DOMContentLoaded event listener (remove old, run new)
document.removeEventListener('DOMContentLoaded', initApp);
document.addEventListener('DOMContentLoaded', initApp);

// Setup Settings and Modals UI Events
document.addEventListener('DOMContentLoaded', () => {
    // Top-level elements
    const inboxMenuBtn = document.getElementById('menu-inbox');
    const settingsMenuBtn = document.getElementById('menu-settings');
    const logoutMenuBtn = document.getElementById('menu-logout');
    
    const dashboardGrid = document.querySelector('.dashboard-grid');
    const settingsPage = document.getElementById('settings-page');
    const settingsBackBtn = document.getElementById('settings-back-btn');
    const pageTitle = document.getElementById('page-title');

    // Navigation
    function showSettings() {
        dashboardGrid.style.display = 'none';
        settingsPage.style.display = 'flex';
        pageTitle.textContent = 'Settings';
        
        document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
        if (settingsMenuBtn) settingsMenuBtn.classList.add('active');
        
        loadSettings();
    }

    function showInbox() {
        dashboardGrid.style.display = 'flex';
        settingsPage.style.display = 'none';
        pageTitle.textContent = 'Inbox';
        
        document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
        if (inboxMenuBtn) inboxMenuBtn.classList.add('active');
    }

    if (settingsMenuBtn) settingsMenuBtn.addEventListener('click', showSettings);
    if (inboxMenuBtn) inboxMenuBtn.addEventListener('click', showInbox);
    if (settingsBackBtn) settingsBackBtn.addEventListener('click', showInbox);
    
    if (logoutMenuBtn) logoutMenuBtn.addEventListener('click', async () => {
        try {
            await fetch('/logout', { method: 'POST' });
            window.location.href = '/login.html';
        } catch(e) { console.error('Logout error', e); }
    });

    // Profile Modal
    const profileBtn = document.getElementById('user-profile-btn');
    const profileModal = document.getElementById('profile-modal');
    const profileCloseBtn = document.getElementById('profile-modal-close');
    
    if (profileBtn) profileBtn.addEventListener('click', () => {
        if (currentAdmin) {
            document.getElementById('profile-name').value = currentAdmin.name || '';
            document.getElementById('profile-email').value = currentAdmin.email || '';
            document.getElementById('profile-phone').value = currentAdmin.phone || '';
            document.getElementById('profile-company').value = currentAdmin.company_name || '';
            document.getElementById('profile-address').value = currentAdmin.business_address || '';
            document.getElementById('profile-password').value = '';
        }
        profileModal.style.display = 'flex';
    });
    
    if (profileCloseBtn) profileCloseBtn.addEventListener('click', () => profileModal.style.display = 'none');
    
    // Handle profile photo upload preview
    let uploadedProfilePhotoBase64 = null;
    const uploadPhotoInput = document.getElementById('upload-profile-photo');
    if (uploadPhotoInput) {
        uploadPhotoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(event) {
                    uploadedProfilePhotoBase64 = event.target.result;
                    document.getElementById('profile-modal-avatar-initial').style.display = 'none';
                    const img = document.getElementById('profile-modal-avatar-img');
                    img.src = uploadedProfilePhotoBase64;
                    img.style.display = 'block';
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // Save Profile
    const saveProfileBtn = document.getElementById('save-profile-btn');
    if (saveProfileBtn) saveProfileBtn.addEventListener('click', async () => {
        const updateData = {
            name: document.getElementById('profile-name').value,
            email: document.getElementById('profile-email').value,
            phone: document.getElementById('profile-phone').value,
            company_name: document.getElementById('profile-company').value,
            business_address: document.getElementById('profile-address').value
        };
        
        const pwd = document.getElementById('profile-password').value;
        if (pwd) {
            updateData.password = pwd;
        }
        
        if (uploadedProfilePhotoBase64) {
            updateData.profile_photo = uploadedProfilePhotoBase64;
        }
        
        saveProfileBtn.disabled = true;
        saveProfileBtn.textContent = 'Saving...';
        
        try {
            const res = await fetch('/admin/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updateData)
            });
            if (res.ok) {
                currentAdmin = await res.json();
                document.getElementById('navbar-username').textContent = currentAdmin.name;
                
                if (currentAdmin.profile_photo) {
                    document.getElementById('navbar-avatar').src = currentAdmin.profile_photo;
                } else {
                    document.getElementById('profile-modal-avatar-initial').textContent = currentAdmin.name.charAt(0).toUpperCase();
                }
                
                profileModal.style.display = 'none';
                showToast('Profile updated successfully', 'success');
            } else {
                showToast('Failed to update profile', 'error');
            }
        } catch(e) {
            showToast('Error updating profile', 'error');
        } finally {
            saveProfileBtn.disabled = false;
            saveProfileBtn.textContent = 'Save Profile';
        }
    });

    // Settings Tabs logic
    const tabs = document.querySelectorAll('.settings-tab');
    const contents = document.querySelectorAll('.settings-content');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            const target = tab.getAttribute('data-target');
            document.getElementById(target).classList.add('active');
            
            if (target === 'settings-team') {
                loadTeamMembers();
            }
        });
    });

    // Fetch and Populate Settings
    async function loadSettings() {
        try {
            const res = await fetch('/settings');
            if (res.ok) {
                currentSettings = await res.json();
                
                // General
                document.getElementById('setting-company').value = currentSettings.company_name || '';
                document.getElementById('setting-business').value = currentSettings.business_name || '';
                
                document.getElementById('setting-business-description').value = currentSettings.business_description || '';
                document.getElementById('setting-business-address').value = currentSettings.business_address || '';
                document.getElementById('setting-business-phone').value = currentSettings.business_phone || '';
                document.getElementById('setting-business-email').value = currentSettings.business_email || '';
                document.getElementById('setting-website-url').value = currentSettings.website_url || '';
                document.getElementById('setting-social-media').value = currentSettings.social_media_links || '';
                document.getElementById('setting-working-hours').value = currentSettings.working_hours || '';

                if (currentSettings.business_logo) {
                    const img = document.getElementById('business-logo-img');
                    if (img) {
                        img.src = currentSettings.business_logo;
                        img.style.display = 'block';
                        document.getElementById('business-logo-icon').style.display = 'none';
                    }
                }
                
                document.getElementById('setting-timezone').value = currentSettings.timezone || 'UTC';
                document.getElementById('setting-language').value = currentSettings.language || 'English';
                document.getElementById('setting-currency').value = currentSettings.currency || 'USD';
                
                // AI
                document.getElementById('setting-ai-enabled').checked = currentSettings.ai_enabled;
                document.getElementById('setting-ai-greeting').value = currentSettings.greeting_message || '';
                document.getElementById('setting-ai-delay').value = currentSettings.ai_reply_delay || 1;
                document.getElementById('setting-ai-max-followups').value = currentSettings.max_followups || 3;
                
                // Notifications
                document.getElementById('setting-notify-desktop').checked = currentSettings.desktop_notifications;
                document.getElementById('setting-notify-email').checked = currentSettings.email_notifications;
                document.getElementById('setting-notify-sound').checked = currentSettings.sound_notifications;
                document.getElementById('setting-notify-alerts').checked = currentSettings.unread_alerts;
            }
        } catch(e) { console.error('Error loading settings', e); }
    }
    
    // Save Generic Settings Wrapper
    async function saveSettings(updateData, btnEl) {
        btnEl.disabled = true;
        const originalText = btnEl.textContent;
        btnEl.textContent = 'Saving...';
        
        try {
            const res = await fetch('/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updateData)
            });
            if (res.ok) {
                currentSettings = await res.json();
                showToast('Settings saved successfully', 'success');
            } else {
                showToast('Failed to save settings', 'error');
            }
        } catch(e) {
            showToast('Error saving settings', 'error');
        } finally {
            btnEl.disabled = false;
            btnEl.textContent = originalText;
        }
    }

    // Business Logo Upload Handler
    let uploadedBusinessLogoBase64 = null;
    const uploadLogoInput = document.getElementById('upload-business-logo');
    if (uploadLogoInput) {
        uploadLogoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(event) {
                    uploadedBusinessLogoBase64 = event.target.result;
                    document.getElementById('business-logo-icon').style.display = 'none';
                    const img = document.getElementById('business-logo-img');
                    img.src = uploadedBusinessLogoBase64;
                    img.style.display = 'block';
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // Save General Settings
    document.getElementById('save-settings-general')?.addEventListener('click', function() {
        const updateData = {
            company_name: document.getElementById('setting-company').value,
            business_name: document.getElementById('setting-business').value,
            business_description: document.getElementById('setting-business-description').value,
            business_address: document.getElementById('setting-business-address').value,
            business_phone: document.getElementById('setting-business-phone').value,
            business_email: document.getElementById('setting-business-email').value,
            website_url: document.getElementById('setting-website-url').value,
            social_media_links: document.getElementById('setting-social-media').value,
            working_hours: document.getElementById('setting-working-hours').value,
            timezone: document.getElementById('setting-timezone').value,
            language: document.getElementById('setting-language').value,
            currency: document.getElementById('setting-currency').value
        };
        
        if (uploadedBusinessLogoBase64) {
            updateData.business_logo = uploadedBusinessLogoBase64;
        }

        const btn = this;
        saveSettings(updateData, btn).then(() => {
            // Update global UI immediately
            if (currentSettings) {
                updateGlobalBranding(currentSettings.company_name, currentSettings.business_logo);
            }
        });
    });

    // Save AI Settings
    document.getElementById('save-settings-ai')?.addEventListener('click', function() {
        saveSettings({
            ai_enabled: document.getElementById('setting-ai-enabled').checked,
            greeting_message: document.getElementById('setting-ai-greeting').value,
            ai_reply_delay: parseInt(document.getElementById('setting-ai-delay').value) || 1,
            max_followups: parseInt(document.getElementById('setting-ai-max-followups').value) || 3
        }, this);
    });

    // Save Notifications
    document.getElementById('save-settings-notifications')?.addEventListener('click', function() {
        saveSettings({
            desktop_notifications: document.getElementById('setting-notify-desktop').checked,
            email_notifications: document.getElementById('setting-notify-email').checked,
            sound_notifications: document.getElementById('setting-notify-sound').checked,
            unread_alerts: document.getElementById('setting-notify-alerts').checked
        }, this);
    });

    // Security Settings
    document.getElementById('save-settings-security')?.addEventListener('click', async function() {
        const username = document.getElementById('setting-security-username').value;
        const password = document.getElementById('setting-security-password').value;
        const confirm = document.getElementById('setting-security-password-confirm').value;
        
        if (password && password !== confirm) {
            showToast('Passwords do not match', 'error');
            return;
        }
        
        const updateData = {};
        if (username) updateData.username = username;
        if (password) updateData.password = password;
        
        if (Object.keys(updateData).length === 0) return;
        
        this.disabled = true;
        this.textContent = 'Updating...';
        
        try {
            const res = await fetch('/admin/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updateData)
            });
            if (res.ok) {
                showToast('Credentials updated successfully', 'success');
                document.getElementById('setting-security-username').value = '';
                document.getElementById('setting-security-password').value = '';
                document.getElementById('setting-security-password-confirm').value = '';
                currentAdmin = await res.json();
            } else {
                showToast('Failed to update credentials', 'error');
            }
        } catch(e) {
            showToast('Error updating credentials', 'error');
        } finally {
            this.disabled = false;
            this.textContent = 'Update Credentials';
        }
    });

    // Appearance / Color Picker Logic
    const colorSwatches = document.querySelectorAll('.color-swatch');
    const customColorPicker = document.getElementById('custom-color-picker');
    
    colorSwatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
            colorSwatches.forEach(s => s.classList.remove('active'));
            swatch.classList.add('active');
            const color = swatch.getAttribute('data-color');
            document.documentElement.style.setProperty('--color-primary', color);
            customColorPicker.value = color;
        });
    });
    
    if (customColorPicker) customColorPicker.addEventListener('input', (e) => {
        colorSwatches.forEach(s => s.classList.remove('active'));
        document.documentElement.style.setProperty('--color-primary', e.target.value);
    });

    document.getElementById('save-settings-appearance')?.addEventListener('click', function() {
        const color = document.documentElement.style.getPropertyValue('--color-primary') || '#6366f1';
        saveSettings({ primary_color: color }, this);
    });

    // Team Members
    const teamModal = document.getElementById('team-modal');
    const teamCloseBtn = document.getElementById('team-modal-close');
    const btnAddTeamMember = document.getElementById('btn-add-team-member');
    const saveTeamBtn = document.getElementById('save-team-btn');
    
    if (teamCloseBtn) teamCloseBtn.addEventListener('click', () => teamModal.style.display = 'none');
    
    if (btnAddTeamMember) btnAddTeamMember.addEventListener('click', () => {
        document.getElementById('team-member-id').value = '';
        document.getElementById('team-name').value = '';
        document.getElementById('team-email').value = '';
        document.getElementById('team-phone').value = '';
        document.getElementById('team-role').value = 'Sales Executive';
        document.getElementById('team-status').value = 'Active';
        document.getElementById('team-modal-title').textContent = 'Add Team Member';
        teamModal.style.display = 'flex';
    });

    async function loadTeamMembers() {
        try {
            const res = await fetch('/team-members');
            if (res.ok) {
                const members = await res.json();
                renderTeamMembers(members);
            }
        } catch(e) { console.error('Error loading team', e); }
    }

    function renderTeamMembers(members) {
        const tbody = document.getElementById('team-members-tbody');
        tbody.innerHTML = '';
        
        if (members.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: var(--text-muted);">No team members found.</td></tr>';
            return;
        }
        
        members.forEach(m => {
            const tr = document.createElement('tr');
            
            // Badge color
            let badgeClass = 'role-sales';
            if (m.role === 'Admin') badgeClass = 'role-admin';
            if (m.role === 'Manager') badgeClass = 'role-manager';
            
            // Status dot
            let statusClass = m.status === 'Active' ? 'status-active' : 'status-inactive';
            
            tr.innerHTML = `
                <td><div style="font-weight: 500; color: var(--text-main);">${m.name}</div></td>
                <td>${m.email}</td>
                <td><span class="team-role-badge ${badgeClass}">${m.role}</span></td>
                <td><span class="status-dot ${statusClass}"></span>${m.status}</td>
                <td>
                    <div class="team-actions">
                        <button class="btn-icon edit-member" data-id="${m.id}" title="Edit"><i class="fa-solid fa-pen"></i></button>
                        <button class="btn-icon delete delete-member" data-id="${m.id}" title="Delete"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
        
        // Add event listeners for edit and delete
        document.querySelectorAll('.edit-member').forEach(btn => {
            btn.addEventListener('click', () => editTeamMember(btn.getAttribute('data-id'), members));
        });
        
        document.querySelectorAll('.delete-member').forEach(btn => {
            btn.addEventListener('click', () => deleteTeamMember(btn.getAttribute('data-id')));
        });
    }

    function editTeamMember(id, members) {
        const m = members.find(member => member.id == id);
        if (m) {
            document.getElementById('team-member-id').value = m.id;
            document.getElementById('team-name').value = m.name;
            document.getElementById('team-email').value = m.email;
            document.getElementById('team-phone').value = m.phone || '';
            document.getElementById('team-role').value = m.role;
            document.getElementById('team-status').value = m.status;
            document.getElementById('team-modal-title').textContent = 'Edit Team Member';
            teamModal.style.display = 'flex';
        }
    }
    
    async function deleteTeamMember(id) {
        if (!confirm('Are you sure you want to delete this team member?')) return;
        
        try {
            const res = await fetch(`/team-members/${id}`, { method: 'DELETE' });
            if (res.ok) {
                showToast('Team member deleted', 'success');
                loadTeamMembers();
            }
        } catch(e) {
            showToast('Error deleting member', 'error');
        }
    }

    if (saveTeamBtn) saveTeamBtn.addEventListener('click', async () => {
        const id = document.getElementById('team-member-id').value;
        const data = {
            name: document.getElementById('team-name').value,
            email: document.getElementById('team-email').value,
            phone: document.getElementById('team-phone').value,
            role: document.getElementById('team-role').value,
            status: document.getElementById('team-status').value
        };
        
        saveTeamBtn.disabled = true;
        saveTeamBtn.textContent = 'Saving...';
        
        try {
            let res;
            if (id) {
                // Update
                res = await fetch(`/team-members/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            } else {
                // Create
                res = await fetch('/team-members', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
            }
            
            if (res.ok) {
                showToast(`Team member ${id ? 'updated' : 'added'} successfully`, 'success');
                teamModal.style.display = 'none';
                loadTeamMembers();
            } else {
                showToast('Failed to save team member', 'error');
            }
        } catch(e) {
            showToast('Error saving member', 'error');
        } finally {
            saveTeamBtn.disabled = false;
            saveTeamBtn.textContent = 'Save Member';
        }
    });

});

// ==========================================
// ANALYTICS PAGE LOGIC
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    const analyticsMenuBtn = document.getElementById('menu-analytics');
    const analyticsPage = document.getElementById('analytics-page');
    const analyticsBackBtn = document.getElementById('analytics-back-btn');
    const analyticsRefreshBtn = document.getElementById('analytics-refresh-btn');
    const dashboardGrid = document.querySelector('.dashboard-grid');
    const settingsPage = document.getElementById('settings-page');
    const pageTitle = document.getElementById('page-title');

    function showAnalytics() {
        dashboardGrid.style.display = 'none';
        settingsPage.style.display = 'none';
        analyticsPage.style.display = 'flex';
        pageTitle.textContent = 'Analytics';
        document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
        if (analyticsMenuBtn) analyticsMenuBtn.classList.add('active');
        loadAnalytics();
    }

    function hideAnalytics() {
        analyticsPage.style.display = 'none';
        dashboardGrid.style.display = 'flex';
        pageTitle.textContent = 'Inbox';
        document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
        document.getElementById('menu-inbox')?.classList.add('active');
    }

    if (analyticsMenuBtn) analyticsMenuBtn.addEventListener('click', showAnalytics);
    if (analyticsBackBtn) analyticsBackBtn.addEventListener('click', hideAnalytics);
    if (analyticsRefreshBtn) analyticsRefreshBtn.addEventListener('click', loadAnalytics);

    document.getElementById('menu-inbox')?.addEventListener('click', () => { if (analyticsPage) analyticsPage.style.display = 'none'; });
    document.getElementById('menu-settings')?.addEventListener('click', () => { if (analyticsPage) analyticsPage.style.display = 'none'; });

    async function loadAnalytics() {
        try {
            const res = await fetch('/api/analytics');
            if (!res.ok) return;
            const data = await res.json();
            renderAnalytics(data);
        } catch(e) { console.error('Analytics load error:', e); }
    }

    function renderAnalytics(data) {
        const s = data.summary;
        document.getElementById('kpi-total-customers').textContent = s.total_customers;
        document.getElementById('kpi-total-pipeline').textContent = '$' + s.total_pipeline.toLocaleString();
        document.getElementById('kpi-total-messages').textContent = s.total_messages;
        document.getElementById('kpi-avg-score').textContent = s.avg_lead_score;
        renderDonut('chart-lead-distribution', [
            { label: 'Hot Leads', value: data.lead_distribution.hot, color: '#ef4444' },
            { label: 'Warm Leads', value: data.lead_distribution.warm, color: '#f59e0b' },
            { label: 'Cold Leads', value: data.lead_distribution.cold, color: '#6366f1' }
        ]);
        renderDonut('chart-ai-vs-human', [
            { label: 'AI Managed', value: data.conversation_management.ai_managed, color: '#10b981' },
            { label: 'Human Managed', value: data.conversation_management.human_managed, color: '#3b82f6' }
        ]);
        renderDonut('chart-message-breakdown', [
            { label: 'Customer', value: data.message_breakdown.customer, color: '#6366f1' },
            { label: 'AI Replies', value: data.message_breakdown.ai, color: '#10b981' },
            { label: 'Human Replies', value: data.message_breakdown.human, color: '#f59e0b' }
        ]);
        renderFunnel('chart-funnel', data.funnel);
        renderPipeline('pipeline-cards', s);
        renderTopCustomers('chart-top-customers', data.top_customers);
        renderProducts('chart-products', data.products);
    }

    function renderDonut(containerId, items) {
        const container = document.getElementById(containerId);
        const total = items.reduce((a, b) => a + b.value, 0);
        if (total === 0) { container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:var(--text-muted);">No data</div>'; return; }
        const radius = 52;
        const circumference = 2 * Math.PI * radius;
        let offset = 0;
        let circles = '';
        items.forEach(item => {
            const pct = item.value / total;
            const dashLength = pct * circumference;
            circles += `<circle cx="70" cy="70" r="${radius}" fill="none" stroke="${item.color}" stroke-width="16" stroke-dasharray="${dashLength} ${circumference - dashLength}" stroke-dashoffset="${-offset}" style="transition: all 0.8s ease;"/>`;
            offset += dashLength;
        });
        const legendItems = items.map(item => {
            const pct = total > 0 ? Math.round(item.value / total * 100) : 0;
            return `<div class="legend-item"><span class="legend-dot" style="background:${item.color};"></span><span>${item.label}</span><span class="legend-value">${item.value} (${pct}%)</span></div>`;
        }).join('');
        container.innerHTML = `<div class="donut-chart"><svg class="donut-svg" viewBox="0 0 140 140"><circle cx="70" cy="70" r="${radius}" fill="none" stroke="var(--border-color)" stroke-width="16"/>${circles}<text x="70" y="66" text-anchor="middle" font-size="22" font-weight="800" fill="var(--text-main)">${total}</text><text x="70" y="82" text-anchor="middle" font-size="10" fill="var(--text-muted)">Total</text></svg><div class="donut-legend">${legendItems}</div></div>`;
    }

    function renderFunnel(containerId, funnelData) {
        const container = document.getElementById(containerId);
        const maxVal = Math.max(...funnelData.map(f => f.count), 1);
        const colors = ['#6366f1', '#818cf8', '#a78bfa', '#c4b5fd', '#ddd6fe', '#10b981', '#34d399', '#6ee7b7'];
        const bars = funnelData.map((item, i) => {
            const pct = (item.count / maxVal) * 100;
            return `<div class="funnel-row"><span class="funnel-label">${item.stage}</span><div class="funnel-bar-container"><div class="funnel-bar" style="width: ${Math.max(pct, 3)}%; background: ${colors[i]};"><span class="funnel-count">${item.count}</span></div></div></div>`;
        }).join('');
        container.innerHTML = `<div class="funnel-bars">${bars}</div>`;
    }

    function renderPipeline(containerId, summary) {
        document.getElementById(containerId).innerHTML = `
            <div class="pipeline-card" style="background: rgba(239,68,68,0.08); color: #ef4444;"><span class="pipeline-label">🔥 Hot Pipeline</span><span class="pipeline-value">$${summary.hot_pipeline.toLocaleString()}</span></div>
            <div class="pipeline-card" style="background: rgba(245,158,11,0.08); color: #f59e0b;"><span class="pipeline-label">🌤 Warm Pipeline</span><span class="pipeline-value">$${summary.warm_pipeline.toLocaleString()}</span></div>
            <div class="pipeline-card" style="background: rgba(99,102,241,0.08); color: #6366f1;"><span class="pipeline-label">💰 Total Pipeline</span><span class="pipeline-value">$${summary.total_pipeline.toLocaleString()}</span></div>`;
    }

    function renderTopCustomers(containerId, customers) {
        const container = document.getElementById(containerId);
        if (!customers || customers.length === 0) { container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);">No data</div>'; return; }
        const rows = customers.map(c => {
            const statusColor = c.status === 'Hot' ? '#ef4444' : c.status === 'Warm' ? '#f59e0b' : '#6366f1';
            const statusBg = c.status === 'Hot' ? 'rgba(239,68,68,0.1)' : c.status === 'Warm' ? 'rgba(245,158,11,0.1)' : 'rgba(99,102,241,0.1)';
            return `<tr><td style="font-weight:600;">${c.name}</td><td>${c.company}</td><td style="font-weight:700;">$${c.budget.toLocaleString()}</td><td><span style="padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600;background:${statusBg};color:${statusColor};">${c.status}</span></td><td style="font-weight:600;">${c.score}/100</td></tr>`;
        }).join('');
        container.innerHTML = `<table class="top-customers-table"><thead><tr><th>Name</th><th>Company</th><th>Budget</th><th>Status</th><th>Score</th></tr></thead><tbody>${rows}</tbody></table>`;
    }

    function renderProducts(containerId, products) {
        const container = document.getElementById(containerId);
        const entries = Object.entries(products);
        if (entries.length === 0) { container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:var(--text-muted);">No data</div>'; return; }
        const maxVal = Math.max(...entries.map(e => e[1]), 1);
        const colors = ['#6366f1', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#d946ef', '#8b5cf6'];
        const bars = entries.map((entry, i) => `<div class="product-bar-row"><div class="product-bar-label"><span>${entry[0]}</span><span style="font-weight:700;">${entry[1]}</span></div><div class="product-bar-track"><div class="product-bar-fill" style="width: ${(entry[1]/maxVal)*100}%; background: ${colors[i%colors.length]};"></div></div></div>`).join('');
        container.innerHTML = `<div class="product-bars">${bars}</div>`;
    }
});
