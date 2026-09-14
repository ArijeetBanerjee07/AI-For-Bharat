/* ============================================
   PMJDY Website — JavaScript Logic
   ============================================ */

document.addEventListener('DOMContentLoaded', () => {

    // ---- ELEMENTS ----
    const form = document.getElementById('pmKisanForm');
    const steps = document.querySelectorAll('.form-step');
    const progressSteps = document.querySelectorAll('.progress-step');
    const progressFill = document.getElementById('progressFill');
    const successOverlay = document.getElementById('successOverlay');
    const successCloseBtn = document.getElementById('successCloseBtn');
    const refNumber = document.getElementById('refNumber');

    let currentStep = 1;
    const totalSteps = 4;

    // ---- HERO PARTICLES ----
    createParticles();

    // ---- SMOOTH SCROLL FOR NAV LINKS ----
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            if (href.startsWith('#')) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
                // Update active state
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                link.classList.add('active');
            }
        });
    });

    // ---- ACTIVE NAV ON SCROLL ----
    const sections = document.querySelectorAll('section[id]');
    window.addEventListener('scroll', () => {
        const scrollPos = window.scrollY + 100;
        sections.forEach(section => {
            const top = section.offsetTop;
            const height = section.offsetHeight;
            const id = section.getAttribute('id');
            if (scrollPos >= top && scrollPos < top + height) {
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                const activeLink = document.querySelector(`.nav-link[href="#${id}"]`);
                if (activeLink) activeLink.classList.add('active');
            }
        });
    });

    // ---- AADHAAR NUMBER FORMATTING ----
    const aadhaarInput = document.getElementById('aadhaarNumber');
    if (aadhaarInput) {
        aadhaarInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length > 12) value = value.slice(0, 12);
            let formatted = '';
            for (let i = 0; i < value.length; i++) {
                if (i > 0 && i % 4 === 0) formatted += ' ';
                formatted += value[i];
            }
            e.target.value = formatted;
        });
    }

    // ---- NUMBER ONLY INPUTS ----
    ['mobile', 'income', 'nomineeAge'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', (e) => {
                e.target.value = e.target.value.replace(/\D/g, '');
                if (id === 'mobile') e.target.value = e.target.value.slice(0, 10);
            });
        }
    });

    // ---- STEP NAVIGATION ----
    document.getElementById('nextStep1').addEventListener('click', () => {
        if (validateStep1()) goToStep(2);
    });

    document.getElementById('nextStep2').addEventListener('click', () => {
        if (validateStep2()) goToStep(3);
    });

    document.getElementById('prevStep2').addEventListener('click', () => goToStep(1));

    document.getElementById('nextStep3').addEventListener('click', () => {
        if (validateStep3()) goToStep(4);
    });

    document.getElementById('prevStep3').addEventListener('click', () => goToStep(2));

    document.getElementById('prevStep4').addEventListener('click', () => goToStep(3));

    function goToStep(step) {
        steps.forEach(s => s.classList.remove('active'));
        document.getElementById(`step${step}`).classList.add('active');

        progressSteps.forEach((ps, i) => {
            ps.classList.remove('active', 'completed');
            if (i + 1 < step) ps.classList.add('completed');
            if (i + 1 === step) ps.classList.add('active');
        });

        progressFill.style.width = `${(step / totalSteps) * 100}%`;
        currentStep = step;
        document.getElementById('apply').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // ---- FILE UPLOAD HANDLING ----
    setupFileUpload('aadhaar', 'aadhaarFile', 'aadhaarDropzone', 'aadhaarDropContent', 'aadhaarPreview', 'aadhaarFileName', 2);
    setupFileUpload('photo', 'photoFile', 'photoDropzone', 'photoDropContent', 'photoPreview', 'photoFileName', 1);

    function setupFileUpload(key, inputId, dropzoneId, contentId, previewId, nameId, maxSizeMB) {
        const input = document.getElementById(inputId);
        const dropzone = document.getElementById(dropzoneId);
        const content = document.getElementById(contentId);
        const preview = document.getElementById(previewId);
        const fileName = document.getElementById(nameId);

        if (!input || !dropzone) return;

        dropzone.addEventListener('click', (e) => {
            if (e.target.closest('.preview-remove')) return;
            input.click();
        });

        input.addEventListener('change', () => {
            if (input.files.length > 0) {
                const file = input.files[0];
                if (file.size > maxSizeMB * 1024 * 1024) {
                    showFieldError(`${inputId}Error`, `File size must be less than ${maxSizeMB}MB`);
                    input.value = '';
                    return;
                }
                clearFieldError(`${inputId}Error`);
                fileName.textContent = file.name;
                content.classList.add('hidden');
                preview.classList.remove('hidden');
            }
        });

        // Remove file
        const removeBtn = preview.querySelector('.preview-remove');
        if (removeBtn) {
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                input.value = '';
                preview.classList.add('hidden');
                content.classList.remove('hidden');
            });
        }
    }

    // ---- FORM SUBMISSION ----
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (!validateStep4()) return;

        const submitBtn = document.getElementById('submitBtn');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoader = submitBtn.querySelector('.btn-loader');

        submitBtn.disabled = true;
        btnText.classList.add('hidden');
        btnLoader.classList.remove('hidden');

        setTimeout(() => {
            submitBtn.disabled = false;
            btnText.classList.remove('hidden');
            btnLoader.classList.add('hidden');

            const ref = window.__customRefNumber || ('PMJDY-' + Date.now().toString(36).toUpperCase() + '-' + Math.random().toString(36).substr(2, 4).toUpperCase());
            refNumber.textContent = ref;

            successOverlay.classList.add('show');
            document.body.style.overflow = 'hidden';
        }, 1000);
    });

    successCloseBtn.addEventListener('click', () => {
        successOverlay.classList.remove('show');
        document.body.style.overflow = '';
        form.reset();
        goToStep(1);
    });

    // ---- VALIDATION ----
    function validateStep1() {
        let valid = true;
        const fields = ['fullName', 'fatherName', 'dob', 'gender', 'aadhaarNumber', 'mobile', 'address', 'state', 'district'];
        clearAllFieldErrors(fields);

        fields.forEach(f => {
            const el = document.getElementById(f);
            if (el && !el.value.trim()) {
                showFieldError(`${f}Error`, 'This field is required');
                el.classList.add('error');
                valid = false;
            }
        });

        const aadhaar = document.getElementById('aadhaarNumber');
        if (aadhaar && aadhaar.value.replace(/\s/g, '').length !== 12) {
            showFieldError('aadhaarNumberError', 'Enter valid 12-digit Aadhaar');
            aadhaar.classList.add('error');
            valid = false;
        }

        return valid;
    }

    function validateStep2() {
        let valid = true;
        const fields = ['occupation', 'income', 'existingAccount'];
        clearAllFieldErrors(fields);

        fields.forEach(f => {
            const el = document.getElementById(f);
            if (el && !el.value.trim()) {
                showFieldError(`${f}Error`, 'Selection required');
                el.classList.add('error');
                valid = false;
            }
        });

        return valid;
    }

    function validateStep3() {
        let valid = true;
        const fields = ['nomineeName', 'nomineeRelation', 'nomineeAge'];
        clearAllFieldErrors(fields);

        fields.forEach(f => {
            const el = document.getElementById(f);
            if (el && !el.value.trim()) {
                showFieldError(`${f}Error`, 'Required');
                el.classList.add('error');
                valid = false;
            }
        });

        return valid;
    }

    function validateStep4() {
        let valid = true;
        const aadhaarFile = document.getElementById('aadhaarFile');
        const photoFile = document.getElementById('photoFile');
        const declaration = document.getElementById('declaration');

        if (!aadhaarFile.files.length && !window.__autoFilledDocs) {
            showFieldError('aadhaarFileError', 'Upload Aadhaar');
            valid = false;
        }
        if (!photoFile.files.length && !window.__autoFilledDocs) {
            showFieldError('photoFileError', 'Upload Photo');
            valid = false;
        }
        if (!declaration.checked && !window.__autoFilledDocs) {
            showFieldError('declarationError', 'Please accept');
            valid = false;
        }
        return valid;
    }

    function showFieldError(errorId, message) {
        const el = document.getElementById(errorId);
        if (el) el.textContent = message;
    }

    function clearFieldError(errorId) {
        const el = document.getElementById(errorId);
        if (el) el.textContent = '';
    }

    function clearAllFieldErrors(fields) {
        fields.forEach(f => {
            clearFieldError(`${f}Error`);
            const input = document.getElementById(f);
            if (input) input.classList.remove('error');
        });
    }

    // ---- HERO PARTICLES ----
    function createParticles() {
        const container = document.getElementById('particles');
        if (!container) return;
        const emojis = ['🏦', '💳', '🏛️', '💸', '💰', '✨'];
        for (let i = 0; i < 15; i++) {
            const particle = document.createElement('div');
            particle.style.cssText = `
                position: absolute;
                font-size: ${12 + Math.random() * 16}px;
                left: ${Math.random() * 100}%;
                top: ${Math.random() * 100}%;
                opacity: 0.15;
                animation: float ${4 + Math.random() * 6}s ease-in-out ${Math.random() * 4}s infinite;
                pointer-events: none;
            `;
            particle.textContent = emojis[Math.floor(Math.random() * emojis.length)];
            container.appendChild(particle);
        }
    }

    const animateElements = document.querySelectorAll('.about-card, .timeline-item, .contact-card, .stat-card');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    animateElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out';
        observer.observe(el);
    });
});

window.addEventListener('message', async (event) => {
    if (event.data && (event.data.type === 'AUTO_FILL' || event.data.type === 'AUTO_FILL_AND_SUBMIT')) {
        const data = event.data.payload || {};
        if (event.data.ref_number) {
            window.__customRefNumber = event.data.ref_number;
        }

        if (window.__isAutoFilling) return;
        window.__isAutoFilling = true;

        const delay = (ms) => new Promise(res => setTimeout(res, ms));
        const typeText = async (id, text) => {
            const el = document.getElementById(id);
            if (el && text !== undefined && text !== null) {
                el.value = '';
                const strText = String(text);
                for (let i = 0; i < strText.length; i++) {
                    el.value += strText[i];
                    await delay(15);
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        };
        const setSelect = (id, val) => {
            const el = document.getElementById(id);
            if (el && val) {
                const strVal = String(val).toLowerCase();
                for (let i = 0; i < el.options.length; i++) {
                    if (el.options[i].value.toLowerCase().includes(strVal) || el.options[i].text.toLowerCase().includes(strVal)) {
                        el.selectedIndex = i;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        break;
                    }
                }
            }
        };

        // Step 1
        if (data.fullName || data.fullname || data.name || data.username) await typeText('fullName', data.fullName || data.fullname || data.name || data.username);
        if (data.fatherName || data.fathername) await typeText('fatherName', data.fatherName || data.fathername);
        if (data.dob) {
            let dob = String(data.dob);
            if (dob.includes('/')) {
                const parts = dob.split('/');
                if (parts[0].length === 2 && parts[2].length === 4) {
                    dob = `${parts[2]}-${parts[1]}-${parts[0]}`;
                }
            }
            const dobEl = document.getElementById('dob');
            if (dobEl) {
                dobEl.value = dob;
                dobEl.dispatchEvent(new Event('change', { bubbles: true }));
            }
            await delay(20);
        }
        if (data.gender) setSelect('gender', data.gender);
        if (data.aadhaarNumber || data.aadhaar || data.aadhar || data.extracted_id) await typeText('aadhaarNumber', data.aadhaarNumber || data.aadhaar || data.aadhar || data.extracted_id);
        if (data.phone || data.mobile) await typeText('mobile', data.phone || data.mobile);
        if (data.address) await typeText('address', data.address);
        if (data.state) setSelect('state', String(data.state).replace(/\s+/g, '_'));
        if (data.district) await typeText('district', data.district);

        await delay(250);
        const nextBtn1 = document.getElementById('nextStep1');
        if (nextBtn1) nextBtn1.click();

        // Step 2
        await delay(250);
        setSelect('occupation', data.occupation || 'Self Employed');
        if (data.income) await typeText('income', typeof data.income === 'string' ? data.income.replace(/\D/g, '') : data.income.toString());
        setSelect('existingAccount', data.existingAccount || 'No');

        await delay(250);
        const nextBtn2 = document.getElementById('nextStep2');
        if (nextBtn2) nextBtn2.click();

        // Step 3
        await delay(250);
        await typeText('nomineeName', data.nomineeName || 'Family Member');
        await typeText('nomineeRelation', data.nomineeRelation || 'Spouse');
        await typeText('nomineeAge', data.nomineeAge || '35');

        await delay(250);
        const nextBtn3 = document.getElementById('nextStep3');
        if (nextBtn3) nextBtn3.click();

        // Step 4 (Docs)
        await delay(350);
        window.__autoFilledDocs = true;

        ['aadhaar', 'photo'].forEach(doc => {
            const wrapper = document.getElementById(`${doc}Dropzone`);
            if (wrapper) {
                const content = wrapper.querySelector('.dropzone-content');
                const preview = wrapper.querySelector('.dropzone-preview');
                if (content) content.classList.add('hidden');
                if (preview) preview.classList.remove('hidden');
            }
            const selEl = document.getElementById(`${doc}FileName`);
            if (selEl) selEl.textContent = `✅ auto-${doc}.pdf`;
        });

        const cb = document.getElementById('declaration');
        if (cb) cb.checked = true;

        await delay(350);
        if (event.data.type === 'AUTO_FILL_AND_SUBMIT' || event.data.autoSubmit) {
            const btn = document.getElementById('submitBtn');
            if (btn) btn.click();
        }

        window.__isAutoFilling = false;
    } else if (event.data && event.data.type === 'AUTO_SUBMIT') {
        if (event.data.ref_number) {
            window.__customRefNumber = event.data.ref_number;
        }
        const btn = document.getElementById('submitBtn');
        if (btn) btn.click();
    }
});

// Notify parent frame that portal is loaded and ready for messages
try {
    window.parent.postMessage({ type: 'PORTAL_READY' }, '*');
} catch (e) {}
