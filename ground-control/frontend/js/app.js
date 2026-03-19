/**
 * Ground Control - Task Management UI
 */

class GroundControl {
    constructor() {
        this.state = {
            buckets: {},
            projects: {},
            task_count: {},
        };
        this.agentTasks = {
            pending: [],
            completed: [],
            status: { connected: false },
        };
        this.ws = null;
        this.currentView = 'kanban';
        this.editingTask = null;
        this.historySortNewest = true;

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupEventListeners();
        this.setupDragAndDrop();
        this.loadVersion();
        this.loadAgentTasks();
    }

    async loadVersion() {
        try {
            const response = await fetch('api/version');
            const data = await response.json();
            const badge = document.getElementById('version-badge');
            if (badge && data.version) {
                badge.textContent = `v${data.version}`;
                badge.title = `Path: ${data.tasks_path}`;
            }
        } catch (error) {
            console.error('Failed to load version:', error);
        }
    }

    async loadAgentTasks() {
        try {
            const response = await fetch('api/agent-tasks');
            const data = await response.json();
            this.agentTasks = data;
            this.renderAgentTasks();
            this.updateAgentTasksBadge();
        } catch (error) {
            console.error('Failed to load agent tasks:', error);
        }
    }

    // WebSocket Connection
    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Use pathname to support ingress (e.g., /api/hassio_ingress/<token>/)
        let basePath = window.location.pathname;
        if (!basePath.endsWith('/')) basePath += '/';
        const wsUrl = `${protocol}//${window.location.host}${basePath}ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected, reconnecting...');
            setTimeout(() => this.connectWebSocket(), 2000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleMessage(message) {
        switch (message.type) {
            case 'state':
                this.state = message.data;
                this.render();
                break;
            case 'task_created':
            case 'task_updated':
            case 'task_moved':
            case 'task_completed':
            case 'task_deleted':
                // Request full state refresh
                this.ws.send(JSON.stringify({ type: 'refresh' }));
                break;
            case 'agent_task_updated':
                // Refresh agent tasks
                this.loadAgentTasks();
                break;
        }
    }

    // Event Listeners
    setupEventListeners() {
        // View tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => this.switchView(tab.dataset.view));
        });

        // New task button
        document.getElementById('new-task-btn').addEventListener('click', () => {
            this.openTaskModal();
        });

        // Modal
        document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
        document.getElementById('modal-cancel').addEventListener('click', () => this.closeModal());
        document.getElementById('task-form').addEventListener('submit', (e) => this.handleTaskSubmit(e));

        // Close modal on outside click
        document.getElementById('task-modal').addEventListener('click', (e) => {
            if (e.target.id === 'task-modal') this.closeModal();
        });

        // Queue tab switching
        document.querySelectorAll('.queue-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.queue-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.queue-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                const queueId = tab.dataset.queue + '-queue';
                document.getElementById(queueId).classList.add('active');
            });
        });

        // Approval modal
        document.getElementById('approval-modal-close')?.addEventListener('click', () => {
            document.getElementById('approval-modal').classList.remove('active');
        });
        document.getElementById('approval-cancel')?.addEventListener('click', () => {
            document.getElementById('approval-modal').classList.remove('active');
        });
        document.getElementById('approval-form')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitApproval();
        });

        // Agent task detail modal
        document.getElementById('agent-task-modal-close')?.addEventListener('click', () => {
            document.getElementById('agent-task-modal').classList.remove('active');
        });
        document.getElementById('agent-task-modal-cancel')?.addEventListener('click', () => {
            document.getElementById('agent-task-modal').classList.remove('active');
        });

        // History filter
        document.getElementById('history-project-filter').addEventListener('change', () => {
            this.renderHistory();
        });

        // History sort toggle
        document.getElementById('history-sort-toggle').addEventListener('click', () => {
            this.historySortNewest = !this.historySortNewest;
            this.updateSortToggle();
            this.renderHistory();
        });
    }

    updateSortToggle() {
        const btn = document.getElementById('history-sort-toggle');
        if (this.historySortNewest) {
            btn.innerHTML = '<span class="sort-icon">↓</span> Newest First';
        } else {
            btn.innerHTML = '<span class="sort-icon">↑</span> Oldest First';
        }
    }

    // Drag and Drop
    setupDragAndDrop() {
        document.addEventListener('dragstart', (e) => {
            if (e.target.classList.contains('task-card')) {
                e.target.classList.add('dragging');
                e.dataTransfer.setData('text/plain', e.target.dataset.taskId);
            }
        });

        document.addEventListener('dragend', (e) => {
            if (e.target.classList.contains('task-card')) {
                e.target.classList.remove('dragging');
            }
        });

        document.addEventListener('dragover', (e) => {
            const dropZone = e.target.closest('.bucket-tasks');
            if (dropZone) {
                e.preventDefault();
                dropZone.classList.add('drag-over');
            }
        });

        document.addEventListener('dragleave', (e) => {
            const dropZone = e.target.closest('.bucket-tasks');
            if (dropZone) {
                dropZone.classList.remove('drag-over');
            }
        });

        document.addEventListener('drop', async (e) => {
            const dropZone = e.target.closest('.bucket-tasks');
            if (dropZone) {
                e.preventDefault();
                dropZone.classList.remove('drag-over');

                const taskId = e.dataTransfer.getData('text/plain');
                const targetBucket = dropZone.dataset.bucket;

                await this.moveTask(taskId, targetBucket);
            }
        });
    }

    // View Switching
    switchView(view) {
        this.currentView = view;

        // Update tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.view === view);
        });

        // Update views
        document.querySelectorAll('.view').forEach(v => {
            v.classList.toggle('active', v.id === `${view}-view`);
        });

        this.render();
    }

    // Rendering
    render() {
        this.renderKanban();
        this.renderProjects();
        this.renderHistory();
        this.updateProjectDropdown();
    }

    renderKanban() {
        const bucketOrder = ['brainstorm', 'planning', 'investigation', 'cleanup', 'work_queue', 'active'];

        bucketOrder.forEach(bucket => {
            const tasks = this.state.buckets[bucket] || [];
            const container = document.querySelector(`.bucket-tasks[data-bucket="${bucket}"]`);
            const countEl = document.querySelector(`.bucket-column[data-bucket="${bucket}"] .bucket-count`);

            if (container) {
                container.innerHTML = tasks.length ? tasks.map(task => this.renderTaskCard(task)).join('') :
                    '<div class="empty-state">No tasks</div>';
            }

            if (countEl) {
                countEl.textContent = tasks.length;
            }
        });

        // Add click handlers for task cards
        document.querySelectorAll('.task-card').forEach(card => {
            card.addEventListener('click', () => {
                const taskId = card.dataset.taskId;
                const task = this.findTask(taskId);
                if (task) this.openTaskModal(task);
            });
        });
    }

    renderTaskCard(task) {
        const isBlocked = task.blocked_by && task.blocked_by.length > 0;
        const blockedClass = isBlocked ? 'blocked' : '';
        const projectClass = task.project ? task.project.replace(/-/g, '-') : '';

        return `
            <div class="task-card ${blockedClass}" data-task-id="${task.id}" draggable="true">
                <div class="task-id">${task.id}</div>
                <div class="task-subject">${this.escapeHtml(task.subject)}</div>
                <div class="task-meta">
                    ${task.project ? `<span class="project-tag ${projectClass}">${task.project}</span>` : ''}
                    ${isBlocked ? `<span class="blocked-indicator">Blocked</span>` : ''}
                </div>
            </div>
        `;
    }

    renderProjects() {
        const container = document.getElementById('projects-list');
        const projects = Object.values(this.state.projects || {});

        if (!projects.length) {
            container.innerHTML = '<div class="empty-state">No projects</div>';
            return;
        }

        container.innerHTML = projects.map(project => {
            const allTasks = this.getTasksForProject(project.slug);
            const completed = allTasks.filter(t => t.bucket === 'completed').length;
            const total = allTasks.length;
            const progress = total > 0 ? Math.round((completed / total) * 100) : 0;

            return `
                <div class="project-card">
                    <div class="project-name">${this.escapeHtml(project.name)}</div>
                    <span class="project-status ${project.status}">${project.status.replace(/_/g, ' ')}</span>
                    <div class="project-goal">${this.escapeHtml(project.goal)}</div>
                    <div class="project-progress">
                        <div class="project-progress-bar" style="width: ${progress}%"></div>
                    </div>
                    <div class="project-stats">
                        <span>${completed} completed</span>
                        <span>${total - completed} remaining</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    formatCompletedDate(dateStr) {
        if (!dateStr) return 'Unknown';

        const parts = dateStr.split(' ');
        const date = parts[0];
        const time = parts[1];

        if (time) {
            return `${date} • ${time}`;
        }
        return date;
    }

    renderHistory() {
        const container = document.getElementById('history-list');
        const filter = document.getElementById('history-project-filter').value;
        let tasks = this.state.buckets['completed'] || [];

        if (filter) {
            tasks = tasks.filter(t => t.project === filter);
        }

        // Sort by completed date (newest or oldest first based on toggle)
        tasks = [...tasks].sort((a, b) => {
            const dateA = a.completed_date || '';
            const dateB = b.completed_date || '';
            return this.historySortNewest
                ? dateB.localeCompare(dateA)
                : dateA.localeCompare(dateB);
        });

        if (!tasks.length) {
            container.innerHTML = '<div class="empty-state">No completed tasks</div>';
            return;
        }

        container.innerHTML = tasks.map(task => `
            <div class="history-item">
                <span class="history-date">${this.formatCompletedDate(task.completed_date)}</span>
                <span class="history-subject">${this.escapeHtml(task.subject)}</span>
                ${task.project ? `<span class="project-tag ${task.project}">${task.project}</span>` : ''}
            </div>
        `).join('');
    }

    updateProjectDropdown() {
        const dropdown = document.getElementById('task-project');
        const historyFilter = document.getElementById('history-project-filter');
        const projects = Object.values(this.state.projects || {});

        const options = '<option value="">None</option>' +
            projects.map(p => `<option value="${p.slug}">${this.escapeHtml(p.name)}</option>`).join('');

        dropdown.innerHTML = options;

        const filterOptions = '<option value="">All Projects</option>' +
            projects.map(p => `<option value="${p.slug}">${this.escapeHtml(p.name)}</option>`).join('');

        historyFilter.innerHTML = filterOptions;
    }

    // Task Operations
    findTask(taskId) {
        for (const bucket of Object.values(this.state.buckets)) {
            const task = bucket.find(t => t.id === taskId);
            if (task) return task;
        }
        return null;
    }

    getTasksForProject(projectSlug) {
        const tasks = [];
        for (const bucket of Object.values(this.state.buckets)) {
            tasks.push(...bucket.filter(t => t.project === projectSlug));
        }
        return tasks;
    }

    async moveTask(taskId, targetBucket) {
        try {
            const response = await fetch(`api/tasks/${taskId}/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bucket: targetBucket }),
            });

            if (!response.ok) {
                const error = await response.json();
                alert(error.error || 'Failed to move task');
            }
        } catch (error) {
            console.error('Error moving task:', error);
            alert('Failed to move task');
        }
    }

    // Modal Operations
    openTaskModal(task = null) {
        this.editingTask = task;

        const modal = document.getElementById('task-modal');
        const title = document.getElementById('modal-title');
        const form = document.getElementById('task-form');

        title.textContent = task ? `Edit Task ${task.id}` : 'New Task';

        // Reset form
        form.reset();

        if (task) {
            document.getElementById('task-id').value = task.id;
            document.getElementById('task-subject').value = task.subject;
            document.getElementById('task-description').value = task.description || '';
            document.getElementById('task-bucket').value = task.bucket;
            document.getElementById('task-project').value = task.project || '';
            document.getElementById('task-blocked-by').value = (task.blocked_by || []).join(', ');
            document.getElementById('blocked-by-group').style.display = 'block';
        } else {
            document.getElementById('task-id').value = '';
            document.getElementById('blocked-by-group').style.display = 'none';
        }

        modal.classList.add('active');
    }

    closeModal() {
        document.getElementById('task-modal').classList.remove('active');
        this.editingTask = null;
    }

    async handleTaskSubmit(e) {
        e.preventDefault();

        const taskId = document.getElementById('task-id').value;
        const data = {
            subject: document.getElementById('task-subject').value.trim(),
            description: document.getElementById('task-description').value.trim(),
            bucket: document.getElementById('task-bucket').value,
            project: document.getElementById('task-project').value,
        };

        if (taskId) {
            // Update existing task
            const blockedBy = document.getElementById('task-blocked-by').value
                .split(',')
                .map(s => s.trim().toUpperCase())
                .filter(s => s);
            data.blocked_by = blockedBy;

            try {
                const response = await fetch(`api/tasks/${taskId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });

                if (!response.ok) {
                    const error = await response.json();
                    alert(error.error || 'Failed to update task');
                    return;
                }
            } catch (error) {
                console.error('Error updating task:', error);
                alert('Failed to update task');
                return;
            }
        } else {
            // Create new task
            try {
                const response = await fetch('api/tasks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });

                if (!response.ok) {
                    const error = await response.json();
                    alert(error.error || 'Failed to create task');
                    return;
                }
            } catch (error) {
                console.error('Error creating task:', error);
                alert('Failed to create task');
                return;
            }
        }

        this.closeModal();
    }

    // Agent Tasks
    renderAgentTasks() {
        this.renderPendingTasks();
        this.renderCompletedTasks();
        this.renderMqttStatus();
    }

    renderPendingTasks() {
        const container = document.getElementById('pending-tasks-list');
        const tasks = this.agentTasks.pending || [];

        if (!tasks.length) {
            container.innerHTML = '<div class="empty-state">No pending tasks</div>';
            return;
        }

        container.innerHTML = tasks.map(task => `
            <div class="agent-task-card pending" data-task-id="${task.task_id}">
                <div class="agent-task-header">
                    <span class="agent-task-id">${task.task_id}</span>
                    <span class="agent-task-from">from ${task.requesting_agent}</span>
                    <span class="agent-task-priority ${task.priority}">${task.priority}</span>
                </div>
                <div class="agent-task-title">${this.escapeHtml(task.title)}</div>
                ${task.description ? `<div class="agent-task-desc">${this.escapeHtml(task.description)}</div>` : ''}
                <div class="agent-task-meta">
                    <span class="agent-task-category">${task.category}</span>
                    <span class="agent-task-time">${task.submitted_at || ''}</span>
                </div>
                <div class="agent-task-actions">
                    <button class="btn btn-small btn-approve" onclick="groundControl.approveTask('${task.task_id}')">
                        ✓ Approve
                    </button>
                    <button class="btn btn-small btn-reject" onclick="groundControl.rejectTask('${task.task_id}')">
                        ✗ Reject
                    </button>
                </div>
            </div>
        `).join('');
    }

    renderCompletedTasks() {
        const container = document.getElementById('completed-tasks-list');
        const tasks = this.agentTasks.completed || [];

        if (!tasks.length) {
            container.innerHTML = '<div class="empty-state">No recent tasks</div>';
            return;
        }

        container.innerHTML = tasks.slice(0, 10).map(task => `
            <div class="agent-task-card ${task.status}">
                <div class="agent-task-header">
                    <span class="agent-task-id">${task.task_id}</span>
                    <span class="agent-task-status ${task.status}">${task.status}</span>
                </div>
                <div class="agent-task-title">${this.escapeHtml(task.title)}</div>
                <div class="agent-task-meta">
                    <span class="agent-task-from">from ${task.requesting_agent}</span>
                </div>
            </div>
        `).join('');
    }

    renderMqttStatus() {
        const statusEl = document.getElementById('mqtt-status');
        if (!statusEl) return;

        const status = this.agentTasks.status || {};
        const dot = statusEl.querySelector('.status-dot');
        const text = statusEl.querySelector('.status-text');

        if (status.connected) {
            dot.className = 'status-dot connected';
            text.textContent = `Connected (${status.pending_count || 0} pending)`;
        } else {
            dot.className = 'status-dot disconnected';
            text.textContent = 'Disconnected';
        }
    }

    updateAgentTasksBadge() {
        const badge = document.getElementById('agent-tasks-badge');
        if (!badge) return;

        const count = (this.agentTasks.pending || []).length;
        badge.textContent = count;
        badge.classList.toggle('hidden', count === 0);
    }

    openApprovalModal(task) {
        document.getElementById('approval-task-id').value = task.task_id;
        document.getElementById('approval-task-title').textContent = task.title;
        document.getElementById('approval-task-description').textContent = task.description || 'No description';
        document.getElementById('approval-task-meta').textContent = `From: ${task.requesting_agent} • Priority: ${task.priority}`;

        // Set default bucket from suggested_bucket if present
        const bucketSelect = document.getElementById('approval-bucket');
        if (task.suggested_bucket && bucketSelect.querySelector(`option[value="${task.suggested_bucket}"]`)) {
            bucketSelect.value = task.suggested_bucket;
        } else {
            bucketSelect.value = 'work_queue';  // Default to work_queue
        }

        document.getElementById('approval-modal').classList.add('active');
    }

    async submitApproval() {
        const taskId = document.getElementById('approval-task-id').value;
        const bucket = document.getElementById('approval-bucket').value;

        try {
            const response = await fetch(`api/agent-tasks/${taskId}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bucket })
            });

            if (response.ok) {
                document.getElementById('approval-modal').classList.remove('active');
                // The WebSocket will update the UI
            }
        } catch (err) {
            console.error('Failed to approve task:', err);
        }
    }

    async approveTask(taskId) {
        // Find the task and open the approval modal
        const task = this.agentTasks.pending.find(t => t.task_id === taskId);
        if (task) {
            this.openApprovalModal(task);
        }
    }

    async rejectTask(taskId) {
        const reason = prompt('Rejection reason (optional):');

        try {
            const response = await fetch(`api/agent-tasks/${taskId}/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: reason || '' }),
            });

            if (response.ok) {
                await this.loadAgentTasks();
            } else {
                const error = await response.json();
                alert(error.error || 'Failed to reject task');
            }
        } catch (error) {
            console.error('Error rejecting task:', error);
            alert('Failed to reject task');
        }
    }

    // Utilities
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.groundControl = new GroundControl();
});
