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
        this.ws = null;
        this.currentView = 'kanban';
        this.editingTask = null;

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupEventListeners();
        this.setupDragAndDrop();
        this.loadVersion();
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

        // History filter
        document.getElementById('history-project-filter').addEventListener('change', () => {
            this.renderHistory();
        });
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

    renderHistory() {
        const container = document.getElementById('history-list');
        const filter = document.getElementById('history-project-filter').value;
        let tasks = this.state.buckets['completed'] || [];

        if (filter) {
            tasks = tasks.filter(t => t.project === filter);
        }

        // Sort by completed date descending
        tasks = [...tasks].sort((a, b) => {
            return (b.completed_date || '').localeCompare(a.completed_date || '');
        });

        if (!tasks.length) {
            container.innerHTML = '<div class="empty-state">No completed tasks</div>';
            return;
        }

        container.innerHTML = tasks.map(task => `
            <div class="history-item">
                <span class="history-date">${task.completed_date || 'Unknown'}</span>
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
