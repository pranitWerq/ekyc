// ===== API Configuration =====
const API_BASE = '';
let authToken = localStorage.getItem('authToken');
let currentUser = null;
let currentSession = null;
let currentStep = 1;
let mediaStream = null;
let isAgentMode = false;
let activeAgentSessionId = null;
let livekitRoom = null;

// ===== API Helper =====
async function api(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers
    });

    if (response.status === 401) {
        handleLogout();
        throw new Error('Session expired');
    }

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || 'Request failed');
    }

    return data;
}

async function apiForm(endpoint, formData) {
    const headers = {};
    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers,
        body: formData
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || 'Request failed');
    }

    return data;
}

// ===== Auth Functions =====
function showLogin() {
    document.getElementById('login-form').classList.remove('hidden');
    document.getElementById('register-form').classList.add('hidden');
}

function showRegister() {
    document.getElementById('login-form').classList.add('hidden');
    document.getElementById('register-form').classList.remove('hidden');
}

async function handleLogin(event) {
    event.preventDefault();

    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    try {
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Login failed');
        }

        authToken = data.access_token;
        localStorage.setItem('authToken', authToken);

        await loadUserAndDashboard();
    } catch (error) {
        alert('Login failed: ' + error.message);
    }
}

async function handleRegister(event) {
    event.preventDefault();

    const fullName = document.getElementById('register-name').value;
    const email = document.getElementById('register-email').value;
    const password = document.getElementById('register-password').value;

    try {
        await api('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ email, password, full_name: fullName })
        });

        alert('Account created! Please login.');
        showLogin();
    } catch (error) {
        alert('Registration failed: ' + error.message);
    }
}

function handleLogout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('authToken');
    stopCamera();
    document.getElementById('auth-view').classList.remove('hidden');
    document.getElementById('dashboard-view').classList.add('hidden');
}

async function loadUserAndDashboard() {
    try {
        currentUser = await api('/auth/me');

        document.getElementById('auth-view').classList.add('hidden');
        document.getElementById('dashboard-view').classList.remove('hidden');

        document.getElementById('user-name').textContent = currentUser.full_name || currentUser.email;
        document.getElementById('user-avatar').textContent = (currentUser.full_name || currentUser.email).charAt(0).toUpperCase();

        // Create or get KYC session
        if (!currentUser.is_admin) {
            document.getElementById('admin-nav').classList.add('hidden');
            await initKYCSession();

            // Check if KYC is already completed or approved
            if (currentSession && (currentSession.status === 'approved' || currentSession.status === 'video_completed')) {
                document.getElementById('verification-nav').classList.add('hidden');
                document.getElementById('status-nav').classList.remove('hidden');
                showSection('status');
                // Set active nav
                document.querySelectorAll('.nav-links a').forEach(l => l.classList.remove('active'));
                const statusLink = document.querySelector('[data-section="status"]');
                if (statusLink) statusLink.classList.add('active');
            } else {
                document.getElementById('verification-nav').classList.remove('hidden');
                document.getElementById('status-nav').classList.remove('hidden');
                showSection('verification');
            }
        } else {
            document.getElementById('admin-nav').classList.remove('hidden');
            document.getElementById('verification-nav').classList.add('hidden');
            document.getElementById('status-nav').classList.add('hidden');
            showSection('admin');
            // Set active nav
            document.querySelectorAll('.nav-links a').forEach(l => l.classList.remove('active'));
            const adminLink = document.querySelector('[data-section="admin"]');
            if (adminLink) adminLink.classList.add('active');
        }

        // Setup navigation
        setupNavigation();

    } catch (error) {
        console.error('Failed to load user:', error);
        handleLogout();
    }
}

// ===== Navigation =====
function setupNavigation() {
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const section = e.target.dataset.section;
            showSection(section);

            document.querySelectorAll('.nav-links a').forEach(l => l.classList.remove('active'));
            e.target.classList.add('active');
        });
    });
}

function showSection(section) {
    if (section === 'admin' && (!currentUser || !currentUser.is_admin)) {
        alert('Unauthorized access');
        return;
    }

    document.getElementById('verification-section').classList.add('hidden');
    document.getElementById('status-section').classList.add('hidden');
    document.getElementById('admin-section').classList.add('hidden');

    document.getElementById(`${section}-section`).classList.remove('hidden');

    if (section === 'status') {
        loadKYCStatus();
    } else if (section === 'admin') {
        loadAdminSessions();
    } else if (section === 'verification') {
        // Reset labels and UI if coming from agent mode
        if (!isAgentMode) {
            document.getElementById('user-back-btn').classList.remove('hidden');
            document.getElementById('agent-back-btn').classList.add('hidden');
            document.querySelector('.stepper').classList.remove('hidden');
            document.querySelectorAll('#step-4 .video-tile-label')[0].textContent = 'You';
            document.querySelectorAll('#step-4 .video-tile-label')[1].textContent = 'Agent';
        }
    }
}

// ===== KYC Session =====
async function initKYCSession() {
    try {
        currentSession = await api('/kyc/sessions', { method: 'POST' });
        updateStepperFromSession();
    } catch (error) {
        console.error('Failed to init session:', error);
    }
}

function updateStepperFromSession() {
    if (!currentSession) return;

    const statusMap = {
        'pending': 1,
        'document_uploaded': 2,
        'face_verified': 3,
        'liveness_passed': 4,
        'video_completed': 4,
        'approved': 4,
        'rejected': 1
    };

    const step = statusMap[currentSession.status] || 1;
    goToStep(step);
}

async function loadKYCStatus() {
    const container = document.getElementById('kyc-status-content');

    try {
        const session = await api('/kyc/sessions/current');

        container.innerHTML = `
            <div class="grid-2">
                <div>
                    <h4 class="mb-2">Session Details</h4>
                    <p><strong>Session ID:</strong> ${session.id}</p>
                    <p><strong>Status:</strong> <span class="badge badge-${getStatusBadge(session.status)}">${session.status}</span></p>
                    <p><strong>Created:</strong> ${new Date(session.created_at).toLocaleString()}</p>
                    <p><strong>Updated:</strong> ${new Date(session.updated_at).toLocaleString()}</p>
                    ${(session.status === 'approved' || session.status === 'video_completed') ? `
                        <div class="alert alert-success mt-4">
                            <span>✅</span>
                            <span>Verification process completed</span>
                        </div>
                    ` : ''}
                </div>
                <div>
                    <h4 class="mb-2">Verification Progress</h4>
                    <div class="flex flex-col gap-1">
                        <div class="flex items-center gap-2">
                            ${session.documents?.length > 0 ? '✅' : '⬜'} Document Uploaded
                        </div>
                        <div class="flex items-center gap-2">
                            ${session.face_verification?.is_match ? '✅' : '⬜'} Face Verified
                        </div>
                        <div class="flex items-center gap-2">
                            ${session.liveness_check?.is_live ? '✅' : '⬜'} Liveness Passed
                        </div>
                        <div class="flex items-center gap-2">
                            ${session.video_session ? '✅' : '⬜'} Video Completed
                        </div>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<p class="text-muted">No active KYC session found. <a href="#" onclick="showSection('verification')">Start verification</a></p>`;
    }
}

function getStatusBadge(status) {
    const badges = {
        'pending': 'pending',
        'document_uploaded': 'info',
        'face_verified': 'info',
        'liveness_passed': 'info',
        'video_completed': 'info',
        'approved': 'success',
        'rejected': 'error'
    };
    return badges[status] || 'pending';
}

// ===== Step Navigation =====
function goToStep(step) {
    if (step < 1 || step > 4) return;

    currentStep = step;

    // Update stepper
    document.querySelectorAll('.step').forEach((s, i) => {
        s.classList.remove('active', 'completed');
        if (i + 1 < step) s.classList.add('completed');
        if (i + 1 === step) s.classList.add('active');
    });

    // Show/hide step content
    for (let i = 1; i <= 4; i++) {
        document.getElementById(`step-${i}`).classList.toggle('hidden', i !== step);
    }

    // Start camera for relevant steps
    stopCamera();
    if (step === 2) {
        startCamera('selfie-video');
    } else if (step === 3) {
        startCamera('liveness-video');
    } else if (step === 4) {
        startCamera('local-video');
        if (!isAgentMode) {
            joinVideoRoom(true); // Join automatically for users
        }
    }
}

// ===== Camera Functions =====
async function startCamera(videoId) {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: 640, height: 480 },
            audio: false
        });
        document.getElementById(videoId).srcObject = mediaStream;
    } catch (error) {
        console.error('Camera error:', error);
        alert('Could not access camera. Please grant camera permissions.');
    }
}

function stopCamera() {
    if (livekitRoom) {
        livekitRoom.disconnect();
        livekitRoom = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    // Explicitly clear video sources
    ['selfie-video', 'liveness-video', 'local-video', 'remote-video'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.srcObject = null;
            if (el.tagName === 'VIDEO') {
                el.pause();
                el.removeAttribute('src');
                el.load();
            }
        }
    });
}

// ===== Document Upload =====
async function handleDocumentUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('document-image').src = e.target.result;
        document.getElementById('document-preview').classList.remove('hidden');
    };
    reader.readAsDataURL(file);

    // Upload to server
    try {
        const formData = new FormData();
        formData.append('document_type', document.getElementById('document-type').value);
        formData.append('file', file);

        const result = await apiForm('/documents/upload', formData);

        // Show extracted data
        document.getElementById('extracted-data').innerHTML = `
            <div class="alert alert-success mb-2">
                <span>✅</span>
                <span>Document processed successfully!</span>
            </div>
            <p><strong>Name:</strong> ${result.extracted_name || 'Not detected'}</p>
            <p><strong>Date of Birth:</strong> ${result.extracted_dob || 'Not detected'}</p>
            <p><strong>ID Number:</strong> ${result.extracted_id_number || 'Not detected'}</p>
        `;

        document.getElementById('next-to-face').disabled = false;

    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

// Drag and drop support
const uploadZone = document.getElementById('document-upload-zone');
if (uploadZone) {
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) {
            document.getElementById('document-input').files = e.dataTransfer.files;
            handleDocumentUpload({ target: { files: [file] } });
        }
    });
}

// ===== Face Verification =====
async function captureSelfie() {
    const video = document.getElementById('selfie-video');
    const canvas = document.getElementById('selfie-canvas');
    const ctx = canvas.getContext('2d');

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);

    // Show preview
    const imageData = canvas.toDataURL('image/jpeg');
    document.getElementById('selfie-image').src = imageData;
    document.getElementById('selfie-preview').classList.remove('hidden');

    // Convert to blob and upload
    canvas.toBlob(async (blob) => {
        try {
            const formData = new FormData();
            formData.append('selfie', blob, 'selfie.jpg');

            const result = await apiForm('/face/verify', formData);

            if (result.is_match) {
                document.getElementById('face-result').innerHTML = `
                    <div class="alert alert-success">
                        <span>✅</span>
                        <span>Face verified! Match score: ${(result.match_score * 100).toFixed(1)}%</span>
                    </div>
                `;
                document.getElementById('next-to-liveness').disabled = false;
            } else {
                document.getElementById('face-result').innerHTML = `
                    <div class="alert alert-error">
                        <span>❌</span>
                        <span>Face does not match. Score: ${(result.match_score * 100).toFixed(1)}%. Please try again.</span>
                    </div>
                `;
            }
        } catch (error) {
            document.getElementById('face-result').innerHTML = `
                <div class="alert alert-error">
                    <span>❌</span>
                    <span>${error.message}</span>
                </div>
            `;
        }
    }, 'image/jpeg', 0.9);
}

// ===== Liveness Detection =====
let livenessCompleted = { blink: false, smile: false };

document.querySelectorAll('.liveness-action').forEach(action => {
    action.addEventListener('click', () => performLivenessCheck(action.dataset.action));
});

async function performLivenessCheck(action) {
    const video = document.getElementById('liveness-video');
    const canvas = document.getElementById('liveness-canvas');
    const ctx = canvas.getContext('2d');

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);

    const imageData = canvas.toDataURL('image/jpeg').split(',')[1];

    try {
        const actionEl = document.getElementById(`${action.replace('_', '-')}-action`);
        actionEl.classList.add('pending');

        const result = await api('/face/liveness/check', {
            method: 'POST',
            body: JSON.stringify({ action, image_data: imageData })
        });

        actionEl.classList.remove('pending');

        if (result[`${action}_detected`] || result.detected) {
            livenessCompleted[action] = true;
            actionEl.classList.add('completed');
        }

        updateLivenessProgress(result);

    } catch (error) {
        document.getElementById(`${action.replace('_', '-')}-action`).classList.remove('pending');
        alert('Liveness check failed: ' + error.message);
    }
}

function updateLivenessProgress(result) {
    const completed = Object.values(livenessCompleted).filter(Boolean).length;
    const total = Object.keys(livenessCompleted).length;

    document.getElementById('liveness-progress-text').textContent = `${completed}/${total}`;
    document.getElementById('liveness-progress-bar').style.width = `${(completed / total) * 100}%`;

    if (result && result.is_live) {
        document.getElementById('liveness-result').innerHTML = `
            <div class="alert alert-success">
                <span>✅</span>
                <span>Liveness verified! Confidence: ${(result.confidence_score * 100).toFixed(1)}%</span>
            </div>
        `;
        document.getElementById('next-to-video').disabled = false;
    }
}

// ===== Video Call =====
async function joinVideoRoom(silent = false) {
    try {
        console.log('Starting joinVideoRoom...');

        // First, make API call to get room credentials
        const result = await api('/video/room', { method: 'POST' });
        console.log('Video room API response:', result);

        document.getElementById('video-status').textContent = 'Connecting...';
        document.getElementById('video-status').className = 'badge badge-info';

        // Check if LiveKit SDK is loaded
        if (typeof LivekitClient === 'undefined' && typeof LiveKit === 'undefined') {
            console.warn('LiveKit SDK not loaded, falling back to local camera only');
            document.getElementById('video-status').textContent = 'Waiting for Agent (Local Mode)';
            document.getElementById('video-status').className = 'badge badge-pending';
            await startCamera('local-video');

            // Toggle buttons
            document.getElementById('join-room-btn').classList.add('hidden');
            document.getElementById('end-call-btn').classList.remove('hidden');
            return;
        }

        // Get the LiveKit object (it can be named LivekitClient or LiveKit)
        const LK = typeof LivekitClient !== 'undefined' ? LivekitClient : LiveKit;
        console.log('Using LiveKit SDK:', LK);

        // Clean up any existing room connection
        if (livekitRoom) {
            await livekitRoom.disconnect();
            livekitRoom = null;
        }

        // Connect to LiveKit
        livekitRoom = new LK.Room({
            adaptiveStream: true,
            dynacast: true,
        });

        // Set up event handlers before connecting
        livekitRoom.on(LK.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            console.log('Track subscribed:', track.kind, 'from', participant.identity);
            if (track.kind === 'video') {
                const remoteEl = document.getElementById('remote-video');
                track.attach(remoteEl);
            } else if (track.kind === 'audio') {
                const audioEl = document.createElement('audio');
                audioEl.id = 'remote-audio-' + participant.identity;
                track.attach(audioEl);
                document.body.appendChild(audioEl);
            }
        });

        livekitRoom.on(LK.RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
            console.log('Track unsubscribed:', track.kind, 'from', participant.identity);
            track.detach();
        });

        livekitRoom.on(LK.RoomEvent.ParticipantConnected, (participant) => {
            console.log('Participant connected:', participant.identity);
            document.getElementById('video-status').textContent = 'Agent Connected';
            document.getElementById('video-status').className = 'badge badge-success';
        });

        livekitRoom.on(LK.RoomEvent.ParticipantDisconnected, (participant) => {
            console.log('Participant disconnected:', participant.identity);
            document.getElementById('video-status').textContent = 'Agent Disconnected';
            document.getElementById('video-status').className = 'badge badge-pending';
        });

        livekitRoom.on(LK.RoomEvent.Disconnected, (reason) => {
            console.log('Disconnected from room:', reason);
            document.getElementById('video-status').textContent = 'Disconnected';
            document.getElementById('video-status').className = 'badge badge-error';
        });

        livekitRoom.on(LK.RoomEvent.ConnectionQualityChanged, (quality, participant) => {
            console.log('Connection quality:', quality, 'for', participant?.identity || 'local');
        });

        // LiveKit Cloud URL from API response or config
        const livekitUrl = result.livekit_url || 'wss://ekyc-x7i2jz1x.livekit.cloud';
        console.log('Connecting to LiveKit server:', livekitUrl);
        console.log('Using token:', result.token?.substring(0, 50) + '...');

        // Connect to the room
        await livekitRoom.connect(livekitUrl, result.token);
        console.log('Connected to LiveKit room:', result.room_name);

        // Enable camera and microphone
        await livekitRoom.localParticipant.enableCameraAndMicrophone();
        console.log('Camera and microphone enabled');

        // Attach local video
        const localVideoTrack = livekitRoom.localParticipant.getTrackPublication(LK.Track.Source.Camera);
        if (localVideoTrack && localVideoTrack.track) {
            localVideoTrack.track.attach(document.getElementById('local-video'));
            console.log('Local video attached');
        }

        document.getElementById('video-status').textContent = 'Waiting for Agent';
        document.getElementById('video-status').className = 'badge badge-pending';

        // Toggle buttons
        document.getElementById('join-room-btn').classList.add('hidden');
        document.getElementById('end-call-btn').classList.remove('hidden');

        if (!silent) {
            console.log('Successfully joined video room!');
        }

        // Start transcription
        const session = await api('/kyc/sessions/current');
        if (session && session.id) {
            startGlobalTranscription(session.id);
        }

    } catch (error) {
        console.error('Video room error:', error);
        document.getElementById('video-status').textContent = 'Connection Failed';
        document.getElementById('video-status').className = 'badge badge-error';

        if (!silent) {
            alert('Failed to join video room: ' + error.message + '\n\nFalling back to local camera mode.');
        }

        // Fallback to local camera only
        await startCamera('local-video');
        document.getElementById('join-room-btn').classList.add('hidden');
        document.getElementById('end-call-btn').classList.remove('hidden');
    }
}

async function endVideoCall() {
    try {
        let sessionId;
        if (isAgentMode && activeAgentSessionId) {
            sessionId = activeAgentSessionId;
            // Admin can end with notes
            const notes = prompt("Enter verification notes:", "Verification successful");
            await api(`/video/room/${sessionId}/end`, {
                method: 'POST',
                body: JSON.stringify({ notes })
            });
        } else {
            const session = await api('/kyc/sessions/current');
            if (session) {
                sessionId = session.id;
            }
        }

        stopCamera();

        document.getElementById('video-status').textContent = 'Call Ended';
        document.getElementById('video-status').className = 'badge badge-info';

        document.getElementById('end-call-btn').classList.add('hidden');
        document.getElementById('join-room-btn').classList.remove('hidden');

        document.getElementById('video-result').classList.remove('hidden');

        alert('Verification call ended.');

        if (isAgentMode) {
            exitAgentCall();
        }

        // Stop transcription
        stopGlobalTranscription();

    } catch (error) {
        console.error('Failed to end call:', error);
        alert('Error: ' + error.message);
    }
}

function toggleAudio() {
    const btn = document.getElementById('toggle-audio');
    if (mediaStream) {
        const audioTrack = mediaStream.getAudioTracks()[0];
        if (audioTrack) {
            audioTrack.enabled = !audioTrack.enabled;
            btn.textContent = audioTrack.enabled ? '🎤' : '🔇';
        }
    }
}

function toggleVideo() {
    const btn = document.getElementById('toggle-video-btn');
    if (mediaStream) {
        const videoTrack = mediaStream.getVideoTracks()[0];
        if (videoTrack) {
            videoTrack.enabled = !videoTrack.enabled;
            btn.textContent = videoTrack.enabled ? '📹' : '📵';
        }
    }
}

// ===== Admin Functions =====
let allSessions = [];
let selectedSessionId = null;

async function loadAdminSessions() {
    try {
        allSessions = await api('/kyc/admin/sessions');
        renderSessionsTable(allSessions);
        updateStats(allSessions);
    } catch (error) {
        console.error('Failed to load sessions:', error);
    }
}

function renderSessionsTable(sessions) {
    const tbody = document.getElementById('sessions-table-body');

    if (sessions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No sessions found</td></tr>';
        return;
    }

    tbody.innerHTML = sessions.map(session => `
        <tr>
            <td><code>${session.id.substring(0, 8)}...</code></td>
            <td>${session.user_id.substring(0, 8)}...</td>
            <td><span class="badge badge-${getStatusBadge(session.status)}">${session.status}</span></td>
            <td>${new Date(session.created_at).toLocaleDateString()}</td>
            <td>
                <button class="btn btn-sm btn-secondary" onclick="reviewSession('${session.id}')">Review</button>
                <button class="btn btn-sm btn-primary" onclick="joinAgentCall('${session.id}')">📹 Join</button>
            </td>
        </tr>
    `).join('');
}

function updateStats(sessions) {
    const pending = sessions.filter(s => !['approved', 'rejected'].includes(s.status)).length;
    const approved = sessions.filter(s => s.status === 'approved').length;
    const rejected = sessions.filter(s => s.status === 'rejected').length;

    document.getElementById('stat-pending').textContent = pending;
    document.getElementById('stat-approved').textContent = approved;
    document.getElementById('stat-rejected').textContent = rejected;
    document.getElementById('stat-total').textContent = sessions.length;
}

function filterSessions(status) {
    const filtered = status ? allSessions.filter(s => s.status === status) : allSessions;
    renderSessionsTable(filtered);
}

async function reviewSession(sessionId) {
    selectedSessionId = sessionId;

    try {
        const session = await api(`/kyc/sessions/${sessionId}`);

        document.getElementById('review-content').innerHTML = `
            <div class="mb-3">
                <p><strong>Session ID:</strong> ${session.id}</p>
                <p><strong>Status:</strong> ${session.status}</p>
                <p><strong>Created:</strong> ${new Date(session.created_at).toLocaleString()}</p>
            </div>
            <h4 class="mb-2">Documents</h4>
            ${session.documents?.length > 0 ? session.documents.map(d => `
                <p>Type: ${d.document_type}, Name: ${d.extracted_name || 'N/A'}</p>
            `).join('') : '<p class="text-muted">No documents</p>'}
            <h4 class="mb-2 mt-3">Face Verification</h4>
            ${session.face_verification ? `
                <p>Match: ${session.face_verification.is_match ? '✅ Yes' : '❌ No'}</p>
                <p>Score: ${(session.face_verification.match_score * 100).toFixed(1)}%</p>
            ` : '<p class="text-muted">Not completed</p>'}
            <h4 class="mb-2 mt-3">Liveness Check</h4>
            ${session.liveness_check ? `
                <p>Live: ${session.liveness_check.is_live ? '✅ Yes' : '❌ No'}</p>
            ` : '<p class="text-muted">Not completed</p>'}
            <div class="form-group mt-3">
                <label class="form-label">Notes</label>
                <textarea id="review-notes" class="form-input" rows="3" placeholder="Add review notes..."></textarea>
            </div>
        `;

        document.getElementById('review-modal').classList.add('active');

    } catch (error) {
        alert('Failed to load session: ' + error.message);
    }
}

function closeModal() {
    document.getElementById('review-modal').classList.remove('active');
    selectedSessionId = null;
}

async function approveSession() {
    await updateSessionStatus('approved');
}

async function rejectSession() {
    await updateSessionStatus('rejected');
}

async function updateSessionStatus(status) {
    if (!selectedSessionId) return;

    try {
        const notes = document.getElementById('review-notes').value;

        await api(`/kyc/admin/sessions/${selectedSessionId}/review`, {
            method: 'PUT',
            body: JSON.stringify({ status, notes })
        });

        closeModal();
        await loadAdminSessions();
        alert(`Session ${status}!`);

    } catch (error) {
        alert('Failed to update session: ' + error.message);
    }
}

async function joinAgentCall(sessionId) {
    try {
        console.log('Agent joining call for session:', sessionId);
        const result = await api(`/video/room/${sessionId}/join-agent`, { method: 'POST' });
        console.log('Agent join API response:', result);

        // Switch to Video View in Agent Mode
        isAgentMode = true;
        activeAgentSessionId = sessionId;

        showSection('verification');
        goToStep(4);

        // Update UI for Agent
        document.getElementById('user-back-btn').classList.add('hidden');
        document.getElementById('agent-back-btn').classList.remove('hidden');
        document.querySelector('.stepper').classList.add('hidden');

        document.querySelectorAll('#step-4 .video-tile-label')[0].textContent = 'Agent (You)';
        document.querySelectorAll('#step-4 .video-tile-label')[1].textContent = 'User (Remote)';

        document.getElementById('video-status').textContent = 'Connecting...';
        document.getElementById('video-status').className = 'badge badge-info';

        // Check if LiveKit SDK is loaded
        if (typeof LivekitClient === 'undefined' && typeof LiveKit === 'undefined') {
            console.warn('LiveKit SDK not loaded, falling back to local camera only');
            document.getElementById('video-status').textContent = 'Connected as Agent (Local Mode)';
            document.getElementById('video-status').className = 'badge badge-success';
            await startCamera('local-video');
            document.getElementById('join-room-btn').classList.add('hidden');
            document.getElementById('end-call-btn').classList.remove('hidden');
            return;
        }

        // Get the LiveKit object (it can be named LivekitClient or LiveKit)
        const LK = typeof LivekitClient !== 'undefined' ? LivekitClient : LiveKit;
        console.log('Agent using LiveKit SDK:', LK);

        // Clean up any existing room connection
        if (livekitRoom) {
            await livekitRoom.disconnect();
            livekitRoom = null;
        }

        // Connect to LiveKit
        livekitRoom = new LK.Room({
            adaptiveStream: true,
            dynacast: true,
        });

        // Set up event handlers before connecting
        livekitRoom.on(LK.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            console.log('Agent: Track subscribed:', track.kind, 'from', participant.identity);
            if (track.kind === 'video') {
                const remoteEl = document.getElementById('remote-video');
                track.attach(remoteEl);
            } else if (track.kind === 'audio') {
                const audioEl = document.createElement('audio');
                audioEl.id = 'remote-audio-agent-' + participant.identity;
                track.attach(audioEl);
                document.body.appendChild(audioEl);
            }
        });

        livekitRoom.on(LK.RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
            console.log('Agent: Track unsubscribed:', track.kind, 'from', participant.identity);
            track.detach();
        });

        livekitRoom.on(LK.RoomEvent.ParticipantConnected, (participant) => {
            console.log('Agent: User connected:', participant.identity);
            document.getElementById('video-status').textContent = 'User Connected';
            document.getElementById('video-status').className = 'badge badge-success';
        });

        livekitRoom.on(LK.RoomEvent.ParticipantDisconnected, (participant) => {
            console.log('Agent: User disconnected:', participant.identity);
            document.getElementById('video-status').textContent = 'User Disconnected';
            document.getElementById('video-status').className = 'badge badge-pending';
        });

        livekitRoom.on(LK.RoomEvent.Disconnected, (reason) => {
            console.log('Agent: Disconnected from room:', reason);
            document.getElementById('video-status').textContent = 'Disconnected';
            document.getElementById('video-status').className = 'badge badge-error';
        });

        // LiveKit Cloud URL
        const livekitUrl = result.livekit_url || 'wss://ekyc-x7i2jz1x.livekit.cloud';
        console.log('Agent connecting to LiveKit server:', livekitUrl);
        console.log('Using token:', result.token?.substring(0, 50) + '...');

        // Connect to the room
        await livekitRoom.connect(livekitUrl, result.token);
        console.log('Agent connected to LiveKit room:', result.room_name);

        // Enable camera and microphone
        await livekitRoom.localParticipant.enableCameraAndMicrophone();
        console.log('Agent: Camera and microphone enabled');

        // Attach local video
        const localVideoTrack = livekitRoom.localParticipant.getTrackPublication(LK.Track.Source.Camera);
        if (localVideoTrack && localVideoTrack.track) {
            localVideoTrack.track.attach(document.getElementById('local-video'));
            console.log('Agent: Local video attached');
        }

        document.getElementById('video-status').textContent = 'Connected as Agent';
        document.getElementById('video-status').className = 'badge badge-success';

        document.getElementById('join-room-btn').classList.add('hidden');
        document.getElementById('end-call-btn').classList.remove('hidden');

        console.log('Agent successfully joined video room!');

        // Start transcription
        startGlobalTranscription(sessionId);

    } catch (error) {
        console.error('Agent join error:', error);
        document.getElementById('video-status').textContent = 'Connection Failed';
        document.getElementById('video-status').className = 'badge badge-error';
        alert('Failed to join call: ' + error.message + '\n\nFalling back to local camera mode.');

        // Fallback to local camera
        await startCamera('local-video');
        document.getElementById('join-room-btn').classList.add('hidden');
        document.getElementById('end-call-btn').classList.remove('hidden');
    }
}

function exitAgentCall() {
    isAgentMode = false;
    stopCamera();
    document.querySelector('.stepper').classList.remove('hidden');
    document.getElementById('agent-back-btn').classList.add('hidden');
    document.getElementById('user-back-btn').classList.remove('hidden');
    showSection('admin');
}


// ===== Transcription Logic =====
let transcriptionSocket = null;
let recognition = null;
let isTranscribing = false;
let currentTranscriptSessionId = null;

async function startGlobalTranscription(sessionId) {
    if (isTranscribing) return;

    currentTranscriptSessionId = sessionId;
    const panel = document.getElementById('transcription-panel');
    panel.classList.remove('hidden');

    // 1. Connect WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/transcription/ws/${sessionId}`;

    try {
        transcriptionSocket = new WebSocket(wsUrl);

        transcriptionSocket.onopen = () => {
            console.log('Transcription WebSocket connected');
            isTranscribing = true;
            startSpeechRecognition();
        };

        transcriptionSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'transcript') {
                appendTranscript(data);
            } else if (data.type === 'status') {
                console.log('Transcription status:', data.message);
            }
        };

        transcriptionSocket.onerror = (error) => {
            console.error('Transcription WebSocket error:', error);
        };

        transcriptionSocket.onclose = () => {
            console.log('Transcription WebSocket closed');
            isTranscribing = false;
            stopSpeechRecognition();
        };

    } catch (error) {
        console.error('Failed to connect transcription socket:', error);
    }
}

function stopGlobalTranscription() {
    if (transcriptionSocket) {
        transcriptionSocket.close();
        transcriptionSocket = null;
    }
    stopSpeechRecognition();
    isTranscribing = false;
    currentTranscriptSessionId = null;
    document.getElementById('transcription-panel').classList.add('hidden');
}

function startSpeechRecognition() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        console.warn('Speech recognition not supported in this browser');
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'auto'; // Will try to detect or use default

    recognition.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }

        if (finalTranscript && transcriptionSocket && transcriptionSocket.readyState === WebSocket.OPEN) {
            transcriptionSocket.send(JSON.stringify({
                type: 'transcript',
                speaker: isAgentMode ? 'agent' : 'user',
                text: finalTranscript,
                language: recognition.lang,
                is_final: true
            }));
        }
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
    };

    recognition.onend = () => {
        if (isTranscribing) {
            // Restart if it stops unexpectedly while session is active
            try {
                recognition.start();
            } catch (e) {
                // Ignore if already started
            }
        }
    };

    try {
        recognition.start();
        console.log('Speech recognition started');
    } catch (error) {
        console.error('Failed to start speech recognition:', error);
    }
}

function stopSpeechRecognition() {
    if (recognition) {
        recognition.stop();
        recognition = null;
    }
}

function appendTranscript(data) {
    const content = document.getElementById('transcript-content');
    const placeholder = content.querySelector('.transcript-placeholder');
    if (placeholder) placeholder.remove();

    const msgDiv = document.createElement('div');
    msgDiv.className = 'transcript-message';

    const timestamp = new Date(data.timestamp).toLocaleTimeString([], { hour12: false });
    const speakerClass = data.speaker === 'agent' ? 'speaker-agent' : 'speaker-user';
    const speakerLabel = data.speaker === 'agent' ? 'Agent' : 'User';

    // Check if translated text exists and is different from original
    const hasTranslation = data.translated_text && data.translated_text !== data.original_text;
    const displayText = hasTranslation ? data.translated_text : data.original_text;
    const originalText = hasTranslation ? `<span class="transcript-original">${data.original_text}</span>` : '';
    const langInfo = data.source_language && data.source_language !== 'en' && data.source_language !== 'auto' ? ` (${data.source_language})` : '';

    msgDiv.innerHTML = `
        <span class="transcript-timestamp">[${timestamp}]</span>
        <span class="transcript-speaker ${speakerClass}">${speakerLabel}${langInfo}:</span>
        <span class="transcript-text">${displayText}</span>
        ${originalText}
    `;

    content.appendChild(msgDiv);
    content.scrollTop = content.scrollHeight;
}

async function downloadTranscript() {
    if (!currentTranscriptSessionId) return;

    try {
        const response = await api(`/transcription/${currentTranscriptSessionId}/download?format=text`);
        const blob = new Blob([response.transcript], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcript_${currentTranscriptSessionId}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (error) {
        console.error('Download failed:', error);
        alert('Failed to download transcript');
    }
}


// ===== Initialization =====
document.addEventListener('DOMContentLoaded', () => {
    if (authToken) {
        loadUserAndDashboard();
    }
});
