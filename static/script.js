document.addEventListener('DOMContentLoaded', () => {
    const generateBtn = document.getElementById('generateBtn');
    const profilePreview = document.getElementById('profilePreview');
    const jobDescTextarea = document.getElementById('jobDescription');
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error');
    const outputSection = document.getElementById('outputSection');
    const generatedResume = document.getElementById('generatedResume');
    const copyBtn = document.getElementById('copyBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const copyBtn2 = document.getElementById('copyBtn2');
    const downloadBtn2 = document.getElementById('downloadBtn2');
    
    // Profile elements
    const profileSelect = document.getElementById('profileSelect');
    const refreshBtn = document.getElementById('refreshBtn');
    const saveCurrentBtn = document.getElementById('saveCurrentBtn');
    const useProfileCheckbox = document.getElementById('useProfileCheckbox');

    if (generateBtn) generateBtn.addEventListener('click', generateResume);
    copyBtn.addEventListener('click', copyToClipboard);
    downloadBtn.addEventListener('click', downloadResume);
    copyBtn2.addEventListener('click', copyToClipboard);
    downloadBtn2.addEventListener('click', downloadResume);
    
    // Profile event listeners
    if (profileSelect) {
        profileSelect.addEventListener('change', onProfileSelect);
    }
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadProfiles);
    }
    if (saveCurrentBtn) {
        saveCurrentBtn.addEventListener('click', saveCurrentResume);
    }

    // Load profiles on page load
    loadProfiles();

    async function loadProfiles() {
        console.log("Profiles")
        console.log('loadProfiles called, profileSelect:', profileSelect);
        try {
            const response = await axios.get('/api/profiles');
            const data = response.data;
            console.log('API Response:', response.status, data);
            
            if (data.profiles) {
                console.log('Profiles found:', data.profiles.length);
                if (!profileSelect) {
                    console.error('profileSelect element not found!');
                    return;
                }
                
                // Clear existing options except the first one
                while (profileSelect.options.length > 1) {
                    profileSelect.remove(1);
                }
                
                // Add profiles
                data.profiles.forEach(profile => {
                    const option = document.createElement('option');
                    option.value = profile.id;
                    option.textContent = profile.name;
                    profileSelect.appendChild(option);
                    console.log('Added profile option:', profile.name, 'ID:', profile.id);
                });
                console.log('Total options now:', profileSelect.options.length);
            } else {
                console.log('No profiles in response or response not ok');
            }
        } catch (error) {
            console.error('Failed to load profiles:', error);
        }
    }

    async function onProfileSelect(event) {
        const profileId = event.target.value;
        profilePreview.textContent = '';
        if (!profileId) return;

        try {
            const response = await axios.get(`/api/profiles/${profileId}`);
            renderProfilePreview(response.data);
        } catch (error) {
            showError('Error loading profile: ' + error.message);
        }
    }

    function renderProfilePreview(profile) {
        if (!profile) {
            profilePreview.textContent = '';
            return;
        }
        const lines = [];
        if (profile.name) lines.push(`<strong>${escapeHtml(profile.name)}</strong>`);
        if (profile.location) lines.push(escapeHtml(profile.location));
        const contact = [];
        if (profile.phone) contact.push(`Phone: ${escapeHtml(profile.phone)}`);
        if (profile.email) contact.push(`Email: ${escapeHtml(profile.email)}`);
        if (profile.linkedin) contact.push(`LinkedIn: ${escapeHtml(profile.linkedin)}`);
        if (contact.length) lines.push(contact.join(' | '));
        if (profile.years_of_experience) lines.push(`Years: ${escapeHtml(String(profile.years_of_experience))}`);

        if (profile.companies && profile.companies.length) {
            lines.push('<em>Companies</em>');
            profile.companies.forEach(c => {
                let row = `${escapeHtml(c.name || '')}`;
                if (c.from || c.to) row += ` (${escapeHtml(c.from || '')} - ${escapeHtml(c.to || '')})`;
                if (c.location) row += ` — ${escapeHtml(c.location)}`;
                lines.push(row);
            });
        }

        if (profile.education && profile.education.length) {
            lines.push('<em>Education</em>');
            profile.education.forEach(e => {
                let row = `${escapeHtml(e.degree || '')}`;
                if (e.school) row += `, ${escapeHtml(e.school)}`;
                if (e.year) row += ` (${escapeHtml(e.year)})`;
                lines.push(row);
            });
        }

        if (profile.resume_text) {
            lines.push('<hr/>');
            lines.push(`<pre>${escapeHtml(profile.resume_text)}</pre>`);
        }

        profilePreview.innerHTML = lines.join('<br/>');
    }

    async function saveCurrentResume() {
        // If a profile is selected, clone it under a new name. Otherwise prompt for resume text.
        const selectedId = profileSelect ? profileSelect.value : null;

        let resumeText = '';

        if (selectedId) {
            // fetch selected profile and use its resume_text
            try {
                const res = await axios.get(`/api/profiles/${selectedId}`);
                const profile = res.data;
                resumeText = profile.resume_text || '';
            } catch (err) {
                showError('Unable to load selected profile: ' + err.message);
                return;
            }
        } else {
            // prompt user for resume text
            resumeText = prompt('Paste resume text to save as a profile:');
            if (!resumeText) return;
        }

        const now = new Date();
        const defaultName = `Resume ${now.toLocaleDateString()}`;
        const profileName = prompt('Enter profile name:', defaultName);
        if (!profileName) return;

        try {
            await axios.post('/api/profiles', { name: profileName, resume_text: resumeText });
            showSuccess('Profile saved successfully!');
            loadProfiles();
        } catch (error) {
            showError('Error saving profile: ' + (error.response?.data?.error || error.message));
        }
    }

    async function generateResume() {
        const jobDescription = jobDescTextarea.value.trim();

        // Validation
        if (!jobDescription) {
            showError('Please enter the job description');
            return;
        }

        // Hide error
        errorDiv.style.display = 'none';
        
        // Show loading
        loadingDiv.style.display = 'block';
        outputSection.style.display = 'none';
        if (generateBtn) generateBtn.disabled = true;

        try {
            // If using profile as input, fetch the selected profile's resume_text
            let body = { jobDescription: jobDescription };
            if (useProfileCheckbox && useProfileCheckbox.checked) {
                const profileId = profileSelect ? profileSelect.value : null;
                if (!profileId) {
                    throw new Error('No profile selected');
                }
                const profRes = await axios.get(`/api/profiles/${profileId}`);
                const profData = profRes.data;
                console.log(profData)
                body.profileResume = profData.resume_text;
                body.profile = profData
            }

            const response = await axios.post('/api/generate', body);
            const data = response.data;

            // Display generated resume
            generatedResume.value = data.generatedResume;
            outputSection.style.display = 'block';
            copyBtn.style.display = 'inline-block';
            downloadBtn.style.display = 'inline-block';
            filename = data.filename;

            // Download generated resume as PDF with the provided filename
            const downloadKey = (data.s3Key || filename).split('/').map(encodeURIComponent).join('/');
            try {
                const downloadResponse = await axios.get(`/download/${downloadKey}`, { responseType: 'blob' });
                const blob = downloadResponse.data;
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            } catch (downloadError) {
                console.error('Failed to download generated resume PDF:', downloadError.message);
            }

            // Scroll to output
            outputSection.scrollIntoView({ behavior: 'smooth' });

        } catch (error) {
            showError(error.message);
        } finally {
            loadingDiv.style.display = 'none';
            if (generateBtn) generateBtn.disabled = false;
        }
    }

    function copyToClipboard() {
        generatedResume.select();
        document.execCommand('copy');
        
        // Show feedback
        const originalText = event.target.textContent;
        event.target.textContent = '✓ Copied!';
        setTimeout(() => {
            event.target.textContent = originalText;
        }, 2000);
    }

    function downloadResume() {
        const element = document.createElement('a');
        element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(generatedResume.value));
        element.setAttribute('download', 'generated_resume.txt');
        element.style.display = 'none';
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
    }

    function showError(message) {
        errorDiv.textContent = '❌ ' + message;
        errorDiv.style.display = 'block';
    }

    function showSuccess(message) {
        const successDiv = document.getElementById('success') || createSuccessDiv();
        successDiv.textContent = '✓ ' + message;
        successDiv.style.display = 'block';
        setTimeout(() => {
            successDiv.style.display = 'none';
        }, 3000);
    }

    function createSuccessDiv() {
        const div = document.createElement('div');
        div.id = 'success';
        div.className = 'success';
        document.querySelector('main').insertBefore(div, document.querySelector('.button-group'));
        return div;
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
