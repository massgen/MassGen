document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element References --- 
    const themeToggle = document.getElementById('theme-toggle');
    const body = document.body;
    const agentsGridContainer = document.querySelector('.agent-cards-container');
    const mobileNavToggle = document.querySelector('.mobile-nav-toggle');
    const mainNav = document.querySelector('.main-nav');
    const header = document.querySelector('.dashboard-header');
    const navLinks = document.querySelectorAll('.nav-list a');
    const modal = document.getElementById('modal');
    const overlay = document.getElementById('overlay');
    const modalCloseButton = document.querySelector('.modal-close-button');
    const modalTitle = document.getElementById('modal-title');
    const modalDescription = document.getElementById('modal-description');
    const agentStatusLive = document.getElementById('agent-status-live');

    // Timeline specific elements
    const timelineSvg = document.getElementById('timelineSvg');
    const timelinePlay = document.getElementById('timelinePlay');
    const timelinePause = document.getElementById('timelinePause');
    const timelineDuration = document.getElementById('timelineDuration');
    const timelineScrubber = document.getElementById('timelineScrubber');
    const comparisonContainer = document.querySelector('.comparison-container');
    const voteButton = document.querySelector('.vote-button');

    // --- 1. Dark/Light Theme Toggle (Requirement 5) ---
    function applyTheme(theme) {
        body.setAttribute('data-theme', theme);
        localStorage.setItem('massgen-theme', theme); // Use a unique key
        // Update scrubber background based on theme for visual consistency
        timelineScrubber.style.backgroundColor = getComputedStyle(document.documentElement).getPropertyValue('--accent-color-' + theme);
    }

    function toggleTheme() {
        const currentTheme = body.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        applyTheme(newTheme);
    }

    // Initialize theme from local storage or default to dark
    const savedTheme = localStorage.getItem('massgen-theme') || 'dark';
    applyTheme(savedTheme);

    themeToggle.addEventListener('click', toggleTheme);
    themeToggle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            toggleTheme();
            e.preventDefault();
        }
    });

    // --- Mobile Navigation Toggle (Requirement 6, part of 1) ---
    mobileNavToggle.addEventListener('click', () => {
        mainNav.classList.toggle('active');
        header.classList.toggle('menu-open');
        const isExpanded = mainNav.classList.contains('active');
        mobileNavToggle.setAttribute('aria-expanded', isExpanded);
        overlay.classList.toggle('active', isExpanded); // Activate overlay with menu
        document.body.style.overflow = isExpanded ? 'hidden' : ''; // Prevent body scroll
    });

    // Close mobile nav when a link is clicked or overlay is clicked
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (mainNav.classList.contains('active')) {
                mainNav.classList.remove('active');
                header.classList.remove('menu-open');
                mobileNavToggle.setAttribute('aria-expanded', false);
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });

    // --- Modal Functionality (Micro-interaction & Accessibility) ---
    function showModal(title, description) {
        modalTitle.textContent = title;
        modalDescription.textContent = description;
        modal.classList.add('active');
        overlay.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden'; // Prevent scrolling background
        modalCloseButton.focus(); // Focus close button for accessibility
    }

    function closeModal() {
        modal.classList.remove('active');
        overlay.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = ''; // Restore scrolling
        // Optionally, return focus to the element that opened the modal
    }

    modalCloseButton.addEventListener('click', closeModal);
    modalCloseButton.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            closeModal();
            e.preventDefault();
        }
    });

    overlay.addEventListener('click', () => {
        if (mainNav.classList.contains('active')) {
            mainNav.classList.remove('active');
            header.classList.remove('menu-open');
            mobileNavToggle.setAttribute('aria-expanded', false);
        }
        if (modal.classList.contains('active')) {
            closeModal();
        }
        overlay.classList.remove('active'); // Ensure overlay closes even if no menu/modal was open
        document.body.style.overflow = '';
    });

    // Close modal if escape key is pressed
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (modal.classList.contains('active')) {
                closeModal();
            } else if (mainNav.classList.contains('active')) {
                mainNav.classList.remove('active');
                header.classList.remove('menu-open');
                mobileNavToggle.setAttribute('aria-expanded', false);
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }
        }
    });

    // --- Mock Data ---
    const AGENT_STATUSES = ['thinking', 'generating', 'voting'];
    const agentsData = [
        { id: 'agent-data-analyst', name: 'Data Analyst', role: 'Thinker', status: 'thinking', description: 'Specializes in analyzing large datasets, identifying patterns, and generating actionable insights. Crucial for initial problem decomposition and strategic planning.' },
        { id: 'agent-code-gen', name: 'Code Generator', role: 'Developer', status: 'generating', description: 'Translates high-level specifications into executable code. Focuses on efficiency, robustness, and adherence to coding standards.' },
        { id: 'agent-qa', name: 'Quality Assurance', role: 'Validator', status: 'voting', description: 'Performs rigorous testing and validation of outputs. Leads the voting process to determine the optimal solution based on predefined criteria.' },
        { id: 'agent-ml-model', name: 'ML Model Trainer', role: 'Scientist', status: 'thinking', description: 'Develops and refines machine learning models, ensuring they are optimized for performance and accuracy in complex scenarios.' },
        { id: 'agent-deployer', name: 'Deployment Handler', role: 'Ops', status: 'generating', description: 'Responsible for the seamless deployment of approved solutions into production environments, managing infrastructure and monitoring.' },
        { id: 'agent-monitor', name: 'System Monitor', role: 'Guardian', status: 'thinking', description: 'Continuously observes system health, resource utilization, and agent performance to detect anomalies and ensure operational stability.' },
        { id: 'agent-router', name: 'Task Router', role: 'Coordinator', status: 'voting', description: 'Directs tasks to appropriate agents based on their capabilities and current workload, optimizing workflow efficiency.' },
    ];

    const TIMELINE_DURATION = 60; // seconds
    let timelineEventsData = [
        { t: 0, label: 'System Init', description: 'Core modules initialized.' },
        { t: 8, label: 'Data Intake', description: 'Initial data streams activated.' },
        { t: 18, label: 'Proposal Gen', description: 'Agent proposals generated.' },
        { t: 28, label: 'Vote Start', description: 'Voting phase initiated.' },
        { t: 40, label: 'Consensus', description: 'Consensus reached on task.' },
        { t: 55, label: 'Finalize', description: 'Final output prepared.' }
    ];
    let currentTime = 0;
    let timelineInterval = null;
    let isTimelinePlaying = false;

    const comparisonOutputsData = [
        { id: 'output-solution-a', agentId: 'agent-code-gen', title: 'Solution A: Optimized Algorithm', content: '```javascript\nfunction processData(data) {\n  // Highly optimized algorithm for data transformation\n  return data.map(item => item * 2);\n}\n```', voteCount: 15 },
        { id: 'output-solution-b', agentId: 'agent-data-analyst', title: 'Solution B: Detailed Report', content: 'Comprehensive report outlining three potential strategies for anomaly detection, including performance metrics and risk assessments.', voteCount: 12 },
        { id: 'output-solution-c', agentId: 'agent-ml-model', title: 'Solution C: ML Model Update', content: 'New model weights and configuration for improved fraud detection, achieving 98% accuracy and reduced false positives.', voteCount: 8 }
    ];

    // --- 2. Render Agent Cards Grid (Requirement 2) ---
    function renderAgentCards() {
        agentsGridContainer.innerHTML = agentsData.map(agent => `
            <div class="agent-card" id="${agent.id}" tabindex="0" role="button" aria-label="Agent ${agent.name} status: ${agent.status}" data-agent-id="${agent.id}">
                <div class="agent-avatar" aria-hidden="true">${agent.name.charAt(0)}</div>
                <span class="status-indicator status-${agent.status}" aria-label="Status: ${agent.status}" role="status"></span>
                <h3>${agent.name}</h3>
                <p>Role: ${agent.role}</p>
                <p>Status: <span class="status-text">${agent.status.charAt(0).toUpperCase() + agent.status.slice(1)}</span></p>
            </div>
        `).join('');

        document.querySelectorAll('.agent-card').forEach(card => {
            card.addEventListener('click', (e) => {
                const agentId = e.currentTarget.dataset.agentId;
                const agent = agentsData.find(a => a.id === agentId);
                if (agent) {
                    showModal(`Agent Details: ${agent.name}`, agent.description);
                }
            });
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.currentTarget.click();
                    e.preventDefault();
                }
            });
        });
    }

    // --- 3. Render Interactive Timeline Visualization (Requirement 3) ---
    function renderTimeline() {
        timelineSvg.innerHTML = ''; // Clear existing SVG elements

        const W = 1000; // viewBox width
        const H = 120;  // viewBox height
        const axisY = 60; // Y-position for the main timeline axis
        const marginX = 40; // Horizontal margin for the timeline line

        // Append the main axis line
        const axisLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        axisLine.setAttribute('x1', marginX);
        axisLine.setAttribute('y1', axisY);
        axisLine.setAttribute('x2', W - marginX);
        axisLine.setAttribute('y2', axisY);
        axisLine.setAttribute('class', 'axis-line'); // Apply CSS class for styling
        timelineSvg.appendChild(axisLine);

        // Append timeline events as ticks and labels
        timelineEventsData.forEach(ev => {
            const x = marginX + ((ev.t / TIMELINE_DURATION) * (W - 2 * marginX));

            const tick = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            tick.setAttribute('x1', x);
            tick.setAttribute('y1', axisY - 6);
            tick.setAttribute('x2', x);
            tick.setAttribute('y2', axisY + 6);
            tick.setAttribute('class', 'event-tick'); // Apply CSS class
            timelineSvg.appendChild(tick);

            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            label.setAttribute('x', x);
            label.setAttribute('y', axisY + 22);
            label.setAttribute('class', 'event-label'); // Apply CSS class
            label.textContent = ev.label;
            timelineSvg.appendChild(label);
        });

        // Update or create the current time indicator (scrubber line)
        const currentX = marginX + ((currentTime / TIMELINE_DURATION) * (W - 2 * marginX));
        let cursor = document.getElementById('currentTimeLine');
        if (!cursor) {
            cursor = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            cursor.setAttribute('id', 'currentTimeLine');
            cursor.setAttribute('y1', axisY - 20);
            cursor.setAttribute('y2', axisY + 20);
            timelineSvg.appendChild(cursor);
        }
        cursor.setAttribute('x1', currentX);
        cursor.setAttribute('x2', currentX);
    }

    function updateTimelineDurationLabel() {
        timelineDuration.textContent = `${currentTime.toFixed(1)}s`;
        timelineScrubber.setAttribute('aria-valuenow', currentTime.toFixed(0));
        
        // Update scrubber position visually
        const W_viewBox = 1000; // Same as viewBox width
        const marginX_viewBox = 40; // Same as marginX used in renderTimeline
        const scrubberPixelPos = (currentTime / TIMELINE_DURATION) * (timelineSvg.clientWidth - 2 * marginX_viewBox) + marginX_viewBox;
        // Adjust for scrubber's own width to center it
        const scrubberOffset = timelineScrubber.offsetWidth / 2;
        timelineScrubber.style.left = `${scrubberPixelPos - scrubberOffset}px`;
    }

    // Scrubber drag to seek timeline
    let draggingScrubber = false;
    function onScrubberDown(e) {
        draggingScrubber = true;
        timelineScrubber.style.cursor = 'grabbing';
        if (timelineInterval) clearInterval(timelineInterval); // Pause timeline when scrubbing
        isTimelinePlaying = false;
        e.preventDefault();
    }
    function onMouseMove(e) {
        if (!draggingScrubber) return;
        const rect = timelineSvg.getBoundingClientRect();
        const marginX_px = 40; // Corresponds to marginX in SVG logic
        // Calculate actual usable width for the timeline (excluding margins)
        const usableWidth = rect.width - (2 * marginX_px);
        // Calculate mouse X position relative to the usable width, clamped within bounds
        const mouseX = Math.max(0, Math.min(e.clientX - rect.left - marginX_px, usableWidth));
        
        const t = (mouseX / usableWidth) * TIMELINE_DURATION;
        currentTime = Math.max(0, Math.min(TIMELINE_DURATION, t));
        updateTimelineDurationLabel();
        renderTimeline();
    }
    function onMouseUp() {
        draggingScrubber = false;
        timelineScrubber.style.cursor = 'grab';
    }

    timelineScrubber.addEventListener('mousedown', onScrubberDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('blur', onMouseUp); // Release scrubber if window loses focus

    // Play/Pause controls
    function stepTimeline() {
        currentTime += 0.2; // Increment by smaller steps for smoother animation
        if (currentTime > TIMELINE_DURATION) {
            currentTime = 0;
        }
        updateTimelineDurationLabel();
        renderTimeline();
    }

    timelinePlay.addEventListener('click', () => {
        if (isTimelinePlaying) return;
        isTimelinePlaying = true;
        timelineInterval = setInterval(stepTimeline, 100); // Faster update for smoother play
    });
    timelinePlay.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            timelinePlay.click();
            e.preventDefault();
        }
    });

    timelinePause.addEventListener('click', () => {
        if (timelineInterval) {
            clearInterval(timelineInterval);
            timelineInterval = null;
        }
        isTimelinePlaying = false;
    });
    timelinePause.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            timelinePause.click();
            e.preventDefault();
        }
    });

    // Keyboard control for scrubber
    timelineScrubber.addEventListener('keydown', (e) => {
        const step = e.shiftKey ? 5 : 1; // Bigger step with Shift key
        if (e.key === 'ArrowRight') {
            currentTime = Math.min(TIMELINE_DURATION, currentTime + step);
            e.preventDefault();
        }
        if (e.key === 'ArrowLeft') {
            currentTime = Math.max(0, currentTime - step);
            e.preventDefault();
        }
        updateTimelineDurationLabel();
        renderTimeline();
    });
    
    // Initial render of timeline elements
    renderTimeline();
    updateTimelineDurationLabel();

    // Resize event listener for timeline scrubber repositioning
    window.addEventListener('resize', updateTimelineDurationLabel);

    // --- 4. Render Comparison Panel for Voting (Requirement 4) ---
    function renderComparisonPanel() {
        comparisonContainer.innerHTML = comparisonOutputsData.map(output => {
            const agent = agentsData.find(a => a.id === output.agentId);
            const agentName = agent ? agent.name : 'Unknown Agent';
            return `
                <div class="agent-output-card" tabindex="0" role="group" aria-labelledby="${output.id}-title" aria-describedby="${output.id}-content ${output.id}-votes">
                    <h3 id="${output.id}-title">${output.title}</h3>
                    <p id="${output.id}-content">Output by: ${agentName}<br>${output.content}</p>
                    <label for="vote-${output.id}">
                        <input type="radio" name="agent-vote" id="vote-${output.id}" value="${output.id}" aria-label="Vote for ${output.title}">
                        Vote (Current: <span id="${output.id}-votes">${output.voteCount}</span> votes)
                    </label>
                </div>
            `;
        }).join('');
    }

    voteButton.addEventListener('click', () => {
        const selectedVote = document.querySelector('input[name="agent-vote"]:checked');
        if (selectedVote) {
            const outputId = selectedVote.value;
            const outputIndex = comparisonOutputsData.findIndex(o => o.id === outputId);
            if (outputIndex > -1) {
                comparisonOutputsData[outputIndex].voteCount++;
                renderComparisonPanel(); // Re-render to update vote count
                alert(`Your vote for '${comparisonOutputsData[outputIndex].title}' has been submitted! Total votes: ${comparisonOutputsData[outputIndex].voteCount}`);
            }
        } else {
            alert('Please select an output to vote for.');
        }
    });

    voteButton.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            voteButton.click();
            e.preventDefault();
        }
    });

    // --- Live Status Updates & Mock Real-time (Animations & Micro-interactions) ---
    function updateLiveStatus() {
        const now = new Date();
        agentStatusLive.textContent = `Last update: ${now.toLocaleTimeString()}`; //
    }
    setInterval(updateLiveStatus, 1000);
    updateLiveStatus();

    // Simulate agent status changes randomly
    setInterval(() => {
        const randomAgentIndex = Math.floor(Math.random() * agentsData.length);
        const currentAgent = agentsData[randomAgentIndex];
        const currentStatusIndex = AGENT_STATUSES.indexOf(currentAgent.status);
        const nextStatusIndex = (currentStatusIndex + 1) % AGENT_STATUSES.length;
        currentAgent.status = AGENT_STATUSES[nextStatusIndex];
        renderAgentCards(); // Re-render to show updated status

        // Occasionally add a new timeline event
        if (Math.random() < 0.2 && timelineEventsData.length < 10) { // 20% chance and max 10 events
            const lastEvent = timelineEventsData[timelineEventsData.length - 1];
            const newTime = Math.min(TIMELINE_DURATION - 5, lastEvent.t + Math.floor(Math.random() * 10) + 5); // Ensure new event is within bounds
            const newEvent = {
                t: newTime,
                label: `Event ${timelineEventsData.length + 1}`,
                description: `Dynamic update: Agent ${currentAgent.name} changed status to ${currentAgent.status}.`
            };
            timelineEventsData.push(newEvent);
            timelineEventsData.sort((a, b) => a.t - b.t); // Keep events sorted by time
            renderTimeline();
        }

    }, 4000); // Update agent statuses every 4 seconds

    // Initial renders
    renderAgentCards();
    renderComparisonPanel();

    // Focus management for initial load - skip link target
    document.querySelector('.skip-link').addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('main-content').focus();
    });
});