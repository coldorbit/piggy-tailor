document.addEventListener('DOMContentLoaded', () => {
    const createBtn = document.getElementById('createBtn');
    const clearBtn = document.getElementById('clearBtn');
    const profileName = document.getElementById('profileName');
    const location = document.getElementById('location');
    const phone = document.getElementById('phone');
    const email = document.getElementById('email');
    const linkedin = document.getElementById('linkedin');
    const yearsOfExperience = document.getElementById('yearsOfExperience');
    const companiesContainer = document.getElementById('companiesContainer');
    const educationContainer = document.getElementById('educationContainer');
    const addCompanyBtn = document.getElementById('addCompanyBtn');
    const addEducationBtn = document.getElementById('addEducationBtn');
    const createError = document.getElementById('createError');
    const createSuccess = document.getElementById('createSuccess');
    const profilesList = document.getElementById('profilesList');
    const emptyState = document.getElementById('emptyState');
    const loadingProfiles = document.getElementById('loadingProfiles');
    // Edit modal elements
    const editModal = document.getElementById('editProfileModal');
    const editProfileName = document.getElementById('editProfileName');
    const editLocation = document.getElementById('editLocation');
    const editPhone = document.getElementById('editPhone');
    const editEmail = document.getElementById('editEmail');
    const editLinkedin = document.getElementById('editLinkedin');
    const editYearsOfExperience = document.getElementById('editYearsOfExperience');
    const editCompaniesContainer = document.getElementById('editCompaniesContainer');
    const editEducationContainer = document.getElementById('editEducationContainer');
    const editAddCompanyBtn = document.getElementById('editAddCompanyBtn');
    const editAddEducationBtn = document.getElementById('editAddEducationBtn');
    const saveEditBtn = document.getElementById('saveEditBtn');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    const editModalClose = document.getElementById('editModalClose');
    let currentEditingId = null;

    createBtn.addEventListener('click', createNewProfile);
    clearBtn.addEventListener('click', clearForm);

    // dynamic company / education controls
    if (addCompanyBtn) addCompanyBtn.addEventListener('click', addCompanyRow);
    if (addEducationBtn) addEducationBtn.addEventListener('click', addEducationRow);

    // start with one row each
    if (companiesContainer && companiesContainer.children.length === 0) addCompanyRow();
    if (educationContainer && educationContainer.children.length === 0) addEducationRow();

    // Load profiles on page load
    loadAllProfiles();

    async function loadAllProfiles() {
        loadingProfiles.style.display = 'block';
        profilesList.innerHTML = '';
        emptyState.style.display = 'none';

        try {
            const response = await axios.get('/api/profiles');
            const data = response.data;

            loadingProfiles.style.display = 'none';

            if (data.profiles && data.profiles.length > 0) {
                profilesList.innerHTML = '';
                data.profiles.forEach(profile => {
                    profilesList.appendChild(createProfileCard(profile));
                });
            } else {
                emptyState.style.display = 'block';
            }
        } catch (error) {
            loadingProfiles.style.display = 'none';
            showCreateError('Failed to load profiles: ' + error.message);
        }
    }

    function createProfileCard(profile) {
        const card = document.createElement('div');
        card.className = 'profile-card';
        
        const created = new Date(profile.created_at).toLocaleDateString();
        const updated = new Date(profile.updated_at).toLocaleDateString();

        card.innerHTML = `
            <div class="profile-card-header">
                <h3>${escapeHtml(profile.name)}</h3>
                <small>Created: ${created} | Updated: ${updated}</small>
            </div>
            <div class="profile-card-actions">
                <button class="btn btn-sm btn-edit" data-id="${profile.id}">Edit</button>
                <button class="btn btn-sm btn-view" data-id="${profile.id}">View</button>
                <button class="btn btn-sm btn-delete" data-id="${profile.id}">Delete</button>
            </div>
        `;

        // Event listeners
        card.querySelector('.btn-edit').addEventListener('click', () => openEditModal(profile.id));
        card.querySelector('.btn-view').addEventListener('click', () => viewProfileById(profile.id));
        card.querySelector('.btn-delete').addEventListener('click', () => deleteProfile(profile.id, profile.name));

        return card;
    }

    async function createNewProfile() {
        const name = profileName.value.trim();
        const loc = location.value.trim();
        const ph = phone.value.trim();
        const em = email.value.trim();
        const li = linkedin.value.trim();
        const years = yearsOfExperience ? yearsOfExperience.value.trim() : '';

        const companies = collectCompanies();
        const education = collectEducation();

        createError.style.display = 'none';
        createSuccess.style.display = 'none';

        if (!name) {
            showCreateError('Profile name is required');
            return;
        }

        // Format the profile into a readable resume text (basic header with contact info + structured lists)
        const resume = formatProfileData(name, loc, ph, em, li, years, companies, education);

        try {
            await axios.post('/api/profiles', { name, location: loc, phone: ph, email: em, linkedin: li, years_of_experience: years, companies, education, resume_text: resume });
            showCreateSuccess('Profile created successfully!');
            clearForm();
            loadAllProfiles();
        } catch (error) {
            showCreateError('Error: ' + (error.response?.data?.error || error.message));
        }
    }

    function formatProfileData(name, loc, ph, em, li, years, companies, education) {
        let resume = `Profile: ${name}\n`;
        resume += '='.repeat(40) + '\n\n';

        if (loc) resume += `Location: ${loc}\n`;
        if (ph) resume += `Phone: ${ph}\n`;
        if (em) resume += `Email: ${em}\n`;
        if (li) resume += `LinkedIn: ${li}\n`;
        if (years) resume += `Years of Experience: ${years}\n`;

        if (companies && companies.length) {
            resume += '\nCompanies:\n';
            companies.forEach(c => {
                resume += `- ${c.name || ''}`;
                if (c.from || c.to) resume += ` (${c.from || ''} - ${c.to || ''})`;
                if (c.location) resume += ` — ${c.location}`;
                resume += '\n';
            });
        }

        if (education && education.length) {
            resume += '\nEducation:\n';
            education.forEach(e => {
                resume += `- ${e.degree || ''}${e.school ? ', ' + e.school : ' '}${e.start_month + '/' + e.start_year + '-' + e.end_month + '/' + e.end_year}` + '\n';
            });
        }

        resume += '\n';
        return resume;
    }

    // Dynamic rows helpers
    function addCompanyRow() {
        if (!companiesContainer) return;
        const idx = companiesContainer.children.length;
        const wrapper = document.createElement('div');
        wrapper.className = 'company-row';
        wrapper.innerHTML = `
            <textarea placeholder="Company name (e.g., Acme Corp)" class="company-name form-control" rows="2" style="width:420px;"></textarea>
            <input placeholder="From (YYYY)" class="company-from form-control" style="width:90px;" />
            <input placeholder="To (YYYY or Present)" class="company-to form-control" style="width:120px;" />
            <textarea placeholder="Location (e.g., San Francisco, CA)" class="company-location form-control" rows="1" style="width:220px;"></textarea>
            <button class="btn btn-sm btn-remove">Remove</button>
        `;
        companiesContainer.appendChild(wrapper);
        wrapper.querySelector('.btn-remove').addEventListener('click', () => wrapper.remove());
    }

    function addEducationRow() {
        if (!educationContainer) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'education-row';
        wrapper.innerHTML = `
            <textarea placeholder="Degree (e.g., B.S. Computer Science)" class="edu-degree form-control" rows="2" style="width:480px;"></textarea>
            <input placeholder="School" class="edu-school form-control" style="width:260px;" />
            <input placeholder="Start Month (e.g., Sep)" class="edu-start-month form-control" style="width:110px;" />
            <input placeholder="Start Year (YYYY)" class="edu-start-year form-control" style="width:100px;" />
            <input placeholder="End Month (e.g., Jun or Present)" class="edu-end-month form-control" style="width:140px;" />
            <input placeholder="End Year (YYYY)" class="edu-end-year form-control" style="width:100px;" />
            <button class="btn btn-sm btn-remove">Remove</button>
        `;
        educationContainer.appendChild(wrapper);
        wrapper.querySelector('.btn-remove').addEventListener('click', () => wrapper.remove());
    }

    function collectCompanies() {
        const rows = Array.from(document.querySelectorAll('.company-row'));
        return rows.map(r => ({
            name: (r.querySelector('.company-name')||{value:''}).value.trim(),
            from: (r.querySelector('.company-from')||{value:''}).value.trim(),
            to: (r.querySelector('.company-to')||{value:''}).value.trim(),
            location: (r.querySelector('.company-location')||{value:''}).value.trim()
        })).filter(c => c.name);
    }

    function collectEducation() {
        const rows = Array.from(document.querySelectorAll('.education-row'));
        return rows.map(r => ({
            degree: (r.querySelector('.edu-degree')||{value:''}).value.trim(),
            school: (r.querySelector('.edu-school')||{value:''}).value.trim(),
            start_month: (r.querySelector('.edu-start-month')||{value:''}).value.trim(),
            start_year: (r.querySelector('.edu-start-year')||{value:''}).value.trim(),
            end_month: (r.querySelector('.edu-end-month')||{value:''}).value.trim(),
            end_year: (r.querySelector('.edu-end-year')||{value:''}).value.trim()
        }));
    }

    async function deleteProfile(id, name) {
        if (!confirm(`Are you sure you want to delete "${name}"?`)) return;

        try {
            await axios.delete(`/api/profiles/${id}`);
            loadAllProfiles();
        } catch (error) {
            showCreateError('Error: ' + (error.response?.data?.error || error.message));
        }
    }

    function openEditModal(id) {
        currentEditingId = id;
        // clear modal
        editProfileName.value = '';
        editLocation.value = '';
        editPhone.value = '';
        editEmail.value = '';
        editLinkedin.value = '';
        editYearsOfExperience.value = '';
        editCompaniesContainer.innerHTML = '';
        editEducationContainer.innerHTML = '';

        axios.get(`/api/profiles/${id}`).then(response => response.data).then(profile => {
            if (profile.error) {
                showCreateError(profile.error || 'Failed to load profile');
                return;
            }
            editProfileName.value = profile.name || '';
            editLocation.value = profile.location || '';
            editPhone.value = profile.phone || '';
            editEmail.value = profile.email || '';
            editLinkedin.value = profile.linkedin || '';
            editYearsOfExperience.value = profile.years_of_experience || '';

            // populate companies
            const comps = profile.companies || [];
            if (comps.length === 0) addEditCompanyRow();
            comps.forEach(c => addEditCompanyRow(c));

            // populate education
            const eds = profile.education || [];
            if (eds.length === 0) addEditEducationRow();
            eds.forEach(e => addEditEducationRow(e));

            // show modal
            editModal.style.display = 'block';
        }).catch(err => showCreateError('Failed to load profile: ' + err.message));
    }

    function closeEditModal() {
        editModal.style.display = 'none';
        currentEditingId = null;
    }

    if (editAddCompanyBtn) editAddCompanyBtn.addEventListener('click', () => addEditCompanyRow());
    if (editAddEducationBtn) editAddEducationBtn.addEventListener('click', () => addEditEducationRow());
    if (saveEditBtn) saveEditBtn.addEventListener('click', submitEditProfile);
    if (cancelEditBtn) cancelEditBtn.addEventListener('click', closeEditModal);
    if (editModalClose) editModalClose.addEventListener('click', closeEditModal);

    function addEditCompanyRow(data) {
        if (!editCompaniesContainer) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'company-row';
        wrapper.innerHTML = `
            <textarea placeholder="Company name (e.g., Acme Corp)" class="company-name form-control" rows="2" style="width:420px;">${data && data.name ? escapeHtml(data.name) : ''}</textarea>
            <input placeholder="From (YYYY)" class="company-from form-control" style="width:90px;" value="${data && data.from ? escapeHtml(data.from) : ''}" />
            <input placeholder="To (YYYY or Present)" class="company-to form-control" style="width:120px;" value="${data && data.to ? escapeHtml(data.to) : ''}" />
            <textarea placeholder="Location (e.g., San Francisco, CA)" class="company-location form-control" rows="1" style="width:220px;">${data && data.location ? escapeHtml(data.location) : ''}</textarea>
            <button class="btn btn-sm btn-remove">Remove</button>
        `;
        editCompaniesContainer.appendChild(wrapper);
        wrapper.querySelector('.btn-remove').addEventListener('click', () => wrapper.remove());
    }

    function addEditEducationRow(data) {
        if (!editEducationContainer) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'education-row';
        wrapper.innerHTML = `
            <textarea placeholder="Degree (e.g., B.S. Computer Science)" class="edu-degree form-control" rows="2" style="width:480px;">${data && data.degree ? escapeHtml(data.degree) : ''}</textarea>
            <input placeholder="School" class="edu-school form-control" style="width:260px;" value="${data && data.school ? escapeHtml(data.school) : ''}" />
            <input placeholder="Start Month (e.g., Sep)" class="edu-start-month form-control" style="width:110px;" value="${data && data.start_month ? escapeHtml(data.start_month) : ''}" />
            <input placeholder="Start Year (YYYY)" class="edu-start-year form-control" style="width:100px;" value="${data && data.start_year ? escapeHtml(data.start_year) : ''}" />
            <input placeholder="End Month (e.g., Jun or Present)" class="edu-end-month form-control" style="width:140px;" value="${data && data.end_month ? escapeHtml(data.end_month) : ''}" />
            <input placeholder="End Year (YYYY)" class="edu-end-year form-control" style="width:100px;" value="${data && data.end_year ? escapeHtml(data.end_year) : ''}" />
            <button class="btn btn-sm btn-remove">Remove</button>
        `;
        editEducationContainer.appendChild(wrapper);
        wrapper.querySelector('.btn-remove').addEventListener('click', () => wrapper.remove());
    }

    function collectEditCompanies() {
        const rows = Array.from(editCompaniesContainer ? editCompaniesContainer.querySelectorAll('.company-row') : []);
        return rows.map(r => ({
            name: (r.querySelector('.company-name')||{value:''}).value.trim(),
            from: (r.querySelector('.company-from')||{value:''}).value.trim(),
            to: (r.querySelector('.company-to')||{value:''}).value.trim(),
            location: (r.querySelector('.company-location')||{value:''}).value.trim()
        })).filter(c => c.name);
    }

    function collectEditEducation() {
        const rows = Array.from(editEducationContainer ? editEducationContainer.querySelectorAll('.education-row') : []);
        return rows.map(r => ({
            degree: (r.querySelector('.edu-degree')||{value:''}).value.trim(),
            school: (r.querySelector('.edu-school')||{value:''}).value.trim(),
            year: (r.querySelector('.edu-year')||{value:''}).value.trim()
        })).filter(e => e.degree || e.school);
    }

    async function submitEditProfile() {
        if (!currentEditingId) return;
        const id = currentEditingId;
        const payload = {
            name: editProfileName.value.trim(),
            location: editLocation.value.trim(),
            phone: editPhone.value.trim(),
            email: editEmail.value.trim(),
            linkedin: editLinkedin.value.trim(),
            years_of_experience: editYearsOfExperience.value.trim(),
            companies: collectEditCompanies(),
            education: collectEditEducation()
        };

        try {
            await axios.put(`/api/profiles/${id}`, payload);
            showCreateSuccess('Profile updated');
            closeEditModal();
            loadAllProfiles();
        } catch (err) {
            showCreateError('Error: ' + (err.response?.data?.error || err.message));
        }
    }

    async function viewProfileById(id) {
        try {
            const res = await axios.get(`/api/profiles/${id}`);
            const profile = res.data;
            viewProfile(profile.resume_text || formatProfileData(profile.name || '', profile.location || '', profile.phone || '', profile.email || '', profile.linkedin || ''));
        } catch (error) {
            showCreateError('Error loading profile: ' + (error.response?.data?.error || error.message));
        }
    }

    function viewProfile(resume) {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Resume Preview</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <pre>${escapeHtml(resume)}</pre>
                <button class="btn btn-primary" onclick="this.closest('.modal').remove()">Close</button>
            </div>
        `;

        modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });

        document.body.appendChild(modal);
    }

    function clearForm() {
        profileName.value = '';
        location.value = '';
        phone.value = '';
        email.value = '';
        linkedin.value = '';
        createError.style.display = 'none';
        createSuccess.style.display = 'none';
    }

    function showCreateError(message) {
        createError.textContent = message;
        createError.style.display = 'block';
    }

    function showCreateSuccess(message) {
        createSuccess.textContent = message;
        createSuccess.style.display = 'block';
    }

    function escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
});
