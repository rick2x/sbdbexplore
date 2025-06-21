class DatabaseViewer {
    constructor() {
        this.databases = [];
        this.currentDatabase = null;
        this.currentTable = null;
        this.currentPage = 1;
        this.perPage = 50;
        this.sortColumn = '';
        this.sortOrder = 'ASC';
        this.searchTerm = '';
        this.searchColumns = ['all'];
        this.tables = [];
        this.loadingTimeout = null;
        this.searchTimeout = null;
        this.lastPaginationInfo = null;
        this.adminEnabled = false;
        this.adminToken = null;
        
        this.initializeEventListeners();
        this.initializeKeyboardShortcuts();
        this.loadDatabases();
    }

    initializeEventListeners() {
        // File upload handling
        const fileInput = document.getElementById('file-input');
        const uploadArea = document.getElementById('upload-area');
        // const refreshBtn = document.getElementById('refresh-btn'); // Removed
        const databaseSelect = document.getElementById('database-select');

        // File input change (both inputs)
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadFile(e.target.files[0]);
            }
        });
        
        const fileInputSimple = document.getElementById('file-input-simple');
        if (fileInputSimple) {
            fileInputSimple.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.uploadFile(e.target.files[0]);
                }
            });
        }

        // Drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadFile(files[0]);
            }
        });

        // Refresh button - REMOVED
        // refreshBtn.addEventListener('click', () => {
        //     this.loadDatabases();
        // });

        // Database selection
        databaseSelect.addEventListener('change', (e) => {
            if (e.target.value) {
                this.selectDatabase(e.target.value);
                this.showDatabaseActions();
            } else {
                this.clearDatabaseSelection();
                this.hideDatabaseActions();
            }
        });

        // Database actions
        const deleteDbBtn = document.getElementById('delete-db-btn');
        const uploadMoreBtn = document.getElementById('upload-more-btn');
        const helpBtn = document.getElementById('help-btn');
        const shortcutsBtn = document.getElementById('shortcuts-btn');
        const searchClear = document.getElementById('search-clear');
        
        deleteDbBtn.addEventListener('click', () => {
            this.confirmDeleteDatabase();
        });
        
        uploadMoreBtn.addEventListener('click', () => {
            document.getElementById('file-input').click();
        });
        
        helpBtn.addEventListener('click', () => {
            this.showHelp();
        });
        
        shortcutsBtn.addEventListener('click', () => {
            this.showKeyboardShortcuts();
        });
        
        searchClear.addEventListener('click', () => {
            searchInput.value = '';
            this.searchTerm = '';
            this.currentPage = 1;
            searchClear.style.display = 'none';
            if (this.currentTable && this.currentDatabase) {
                this.loadTableData(this.currentDatabase, this.currentTable);
            }
        });

        // Search functionality
        const searchInput = document.getElementById('search-input');
        let searchTimeout;
        
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const value = e.target.value;
            
            // Show/hide clear button
            if (value) {
                searchClear.style.display = 'flex';
            } else {
                searchClear.style.display = 'none';
            }
            
            searchTimeout = setTimeout(() => {
                this.searchTerm = value;
                this.currentPage = 1;
                if (this.currentTable && this.currentDatabase) {
                    this.loadTableData(this.currentDatabase, this.currentTable);
                }
            }, 300);
        });

        // Per page selection
        const perPageSelect = document.getElementById('per-page-select');
        perPageSelect.addEventListener('change', (e) => {
            this.perPage = parseInt(e.target.value);
            this.currentPage = 1;
            if (this.currentTable && this.currentDatabase) {
                this.loadTableData(this.currentDatabase, this.currentTable);
            }
        });

        // Export button
        const exportBtn = document.getElementById('export-btn');
        exportBtn.addEventListener('click', () => {
            this.exportTable();
        });
    }

    initializeKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Only handle shortcuts when not typing in input fields
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
                return;
            }

            switch(e.key) {
                case 'u':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        document.getElementById('file-input').click();
                    }
                    break;
                case 'f':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        const searchInput = document.getElementById('search-input');
                        if (searchInput) {
                            searchInput.focus();
                        }
                    }
                    break;
                case 'Escape':
                    // Clear search
                    const searchInput = document.getElementById('search-input');
                    if (searchInput && searchInput.value) {
                        searchInput.value = '';
                        this.searchTerm = '';
                        this.currentPage = 1;
                        document.getElementById('search-clear').style.display = 'none';
                        if (this.currentTable && this.currentDatabase) {
                            this.loadTableData(this.currentDatabase, this.currentTable);
                        }
                    }
                    break;
                case 'ArrowLeft':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        this.navigatePage(-1);
                    }
                    break;
                case 'ArrowRight':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        this.navigatePage(1);
                    }
                    break;
                case 'e':
                    if ((e.ctrlKey || e.metaKey) && this.currentTable) {
                        e.preventDefault();
                        this.exportTable();
                    }
                    break;
                case '?':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        this.showKeyboardShortcuts();
                    }
                    break;
            }
        });
    }

    navigatePage(direction) {
        if (!this.currentTable || !this.currentDatabase) return;
        
        const newPage = this.currentPage + direction;
        
        // Get current pagination info from the last loaded data
        const paginationInfo = this.lastPaginationInfo;
        const maxPage = paginationInfo ? paginationInfo.total_pages : 1;
        
        // Ensure we stay within valid page bounds
        if (newPage >= 1 && newPage <= maxPage) {
            this.currentPage = newPage;
            this.loadTableData(this.currentDatabase, this.currentTable);
        } else {
            // Provide feedback when trying to navigate beyond bounds
            if (newPage < 1) {
                this.showToast('info', 'Navigation', 'Already on the first page');
            } else if (newPage > maxPage) {
                this.showToast('info', 'Navigation', `Already on the last page (${maxPage})`);
            }
        }
    }

    async loadDatabases() {
        try {
            const response = await fetch('/databases');
            const result = await response.json();

            if (result.success) {
                this.databases = result.databases;
                this.adminEnabled = result.admin_enabled || false;
                this.populateDatabaseSelect();
                
                if (this.databases.length > 0) {
                    this.showExplorerSection();
                } else {
                    // Show hero section if no databases
                    this.showHeroSection();
                }
            } else {
                this.showToast('error', 'Load Failed', 'Failed to load databases');
            }
        } catch (error) {
            console.error('Load databases error:', error);
            this.showToast('error', 'Load Failed', 'Network error occurred while loading databases');
        }
    }

    populateDatabaseSelect() {
        const databaseSelect = document.getElementById('database-select');
        
        // Store current selection
        const currentValue = databaseSelect.value;
        
        // Clear existing options except the first one
        databaseSelect.innerHTML = '<option value="">Select a database...</option>';
        
        this.databases.forEach(db => {
            const option = document.createElement('option');
            option.value = db.filename;
            const fileSize = this.formatFileSize(db.file_size);
            const uploadDate = new Date(db.modified_time).toLocaleDateString();
            option.textContent = `${db.original_name} (${db.table_count} tables, ${fileSize})`;
            option.title = `Uploaded: ${uploadDate}`;
            databaseSelect.appendChild(option);
        });
        
        // Restore selection if database still exists
        if (currentValue && this.databases.find(db => db.filename === currentValue)) {
            databaseSelect.value = currentValue;
        }
    }

    async uploadFile(file) {
        // Validate file type
        const allowedExtensions = ['.mdb', '.accdb', '.sqlite', '.db'];
        const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
        
        if (!allowedExtensions.includes(fileExtension)) {
            this.showToast('error', 'Invalid File Type', 'Please select a .mdb, .accdb, .sqlite, or .db file');
            return;
        }

        // Check file size (100MB limit)
        if (file.size > 100 * 1024 * 1024) {
            this.showToast('error', 'File Too Large', 'File size must be less than 100MB');
            return;
        }

        // Show progress indicator
        this.showUploadProgress(file.name, file.size);

        const formData = new FormData();
        formData.append('file', file);
        // formData.append('csrf_token', document.querySelector('meta[name="csrf-token"]').getAttribute('content')); // Alternative: send as form field

        try {
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
            const response = await fetch('/upload', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('success', 'Upload Successful', `Database "${file.name}" uploaded successfully`);
                
                // Reload databases and auto-select the new one
                await this.loadDatabases();
                
                // Auto-select the newly uploaded database
                const databaseSelect = document.getElementById('database-select');
                databaseSelect.value = result.database.filename;
                this.selectDatabase(result.database.filename);
                
                // Ensure we're in explorer mode, not upload mode
                this.showExplorerSection();
                
            } else {
                this.showToast('error', 'Upload Failed', result.error || 'Failed to upload database');
            }
        } catch (error) {
            console.error('Upload error:', error);
            this.showToast('error', 'Upload Failed', 'Network error occurred during upload');
        } finally {
            this.hideUploadProgress();
            // Reset file input
            document.getElementById('file-input').value = '';
            const fileInputSimple = document.getElementById('file-input-simple');
            if (fileInputSimple) fileInputSimple.value = '';
        }
    }

    showUploadProgress(filename, fileSize) {
        const overlay = document.getElementById('loading-overlay');
        const content = overlay.querySelector('.loading-content');
        
        content.innerHTML = `
            <div class="upload-progress">
                <i class="fas fa-upload" style="font-size: 2rem; color: var(--primary-color); margin-bottom: 1rem;"></i>
                <h3>Uploading Database</h3>
                <p class="upload-filename">${filename}</p>
                <p class="upload-size">${this.formatFileSize(fileSize)}</p>
                <div class="progress-bar">
                    <div class="progress-fill"></div>
                </div>
                <p class="upload-status">Preparing upload...</p>
            </div>
        `;
        
        overlay.style.display = 'flex';
        
        // Simulate progress for user feedback
        let progress = 0;
        const progressBar = overlay.querySelector('.progress-fill');
        const statusText = overlay.querySelector('.upload-status');
        
        const updateProgress = () => {
            progress += Math.random() * 15 + 5;
            if (progress > 90) progress = 90;
            
            progressBar.style.width = `${progress}%`;
            
            if (progress < 30) {
                statusText.textContent = 'Uploading file...';
            } else if (progress < 70) {
                statusText.textContent = 'Processing database...';
            } else {
                statusText.textContent = 'Almost done...';
            }
        };
        
        this.progressInterval = setInterval(updateProgress, 200);
    }

    hideUploadProgress() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
        this.hideLoadingOverlay();
    }

    showHeroSection() {
        document.getElementById('hero-section').style.display = 'block';
        document.getElementById('upload-section').style.display = 'none';
        document.getElementById('explorer-section').style.display = 'none';
        // document.getElementById('refresh-btn').style.display = 'none'; // Removed
    }
    
    showExplorerSection() {
        document.getElementById('hero-section').style.display = 'none';
        document.getElementById('upload-section').style.display = 'none'; // Hide upload section when databases exist
        document.getElementById('explorer-section').style.display = 'block';
        // document.getElementById('refresh-btn').style.display = 'flex'; // Removed
    }

    showUploadSection() {
        document.getElementById('hero-section').style.display = 'none';
        document.getElementById('upload-section').style.display = 'flex';
        document.getElementById('explorer-section').style.display = 'none';
        // document.getElementById('refresh-btn').style.display = 'none'; // Removed
    }

    async selectDatabase(databaseId) {
        this.currentDatabase = databaseId;
        this.currentTable = null;
        
        // Find database info
        const dbInfo = this.databases.find(db => db.filename === databaseId);
        if (!dbInfo) {
            this.showToast('error', 'Database Error', 'Database information not found');
            return;
        }

        // Update database info display
        const databaseName = document.getElementById('database-name');
        const tableCount = document.getElementById('table-count');
        if (databaseName) databaseName.textContent = dbInfo.original_name;
        if (tableCount) tableCount.textContent = `${this.formatFileSize(dbInfo.file_size)}`;

        try {
            // Load tables for this database
            const response = await fetch(`/database/${encodeURIComponent(databaseId)}/tables`);
            const result = await response.json();

            if (result.success) {
                this.tables = result.tables;
                if (tableCount) tableCount.textContent = `${this.formatFileSize(dbInfo.file_size)} • ${result.tables.length} tables`;
                this.showTablesSection();
                this.populateTableList();
                this.updateWelcomeMessage('table');
            } else {
                this.showToast('error', 'Load Failed', result.error || 'Failed to load tables');
            }
        } catch (error) {
            console.error('Load tables error:', error);
            this.showToast('error', 'Load Failed', 'Network error occurred while loading tables');
        }
    }

    clearDatabaseSelection() {
        this.currentDatabase = null;
        this.currentTable = null;
        this.tables = [];
        
        document.getElementById('tables-section').style.display = 'none';
        document.getElementById('table-viewer').style.display = 'none';
        this.updateWelcomeMessage('database');
        this.hideDatabaseActions();
    }

    showTablesSection() {
        const tablesSection = document.getElementById('tables-section');
        if (tablesSection) {
            tablesSection.style.display = 'block';
        }
    }

    updateWelcomeMessage(type) {
        const welcomeMessage = document.getElementById('welcome-message');
        const welcomeContent = document.getElementById('welcome-content');
        
        welcomeMessage.style.display = 'flex';
        document.getElementById('table-viewer').style.display = 'none';
        
        if (type === 'database') {
            welcomeContent.className = 'welcome-content';
            welcomeContent.innerHTML = `
                <i class="fas fa-database"></i>
                <h3>Select a database to begin</h3>
                <p>Choose a database from the dropdown to explore its contents</p>
            `;
        } else if (type === 'table') {
            welcomeContent.className = 'welcome-content table-selection';
            welcomeContent.innerHTML = `
                <i class="fas fa-arrow-left"></i>
                <h3>Select a table to view its contents</h3>
                <p>Choose a table from the sidebar to explore your database</p>
            `;
        }
    }

    populateTableList() {
        const tableList = document.getElementById('table-list');
        if (!tableList) {
            console.error('Table list element not found');
            return;
        }
        
        tableList.innerHTML = '';

        // Add table search functionality (only once)
        const tableSearch = document.getElementById('table-search');
        if (tableSearch && !tableSearch.hasAttribute('data-listener-added')) {
            tableSearch.addEventListener('input', (e) => {
                this.filterTables(e.target.value.toLowerCase());
            });
            tableSearch.setAttribute('data-listener-added', 'true');
        }

        if (!this.tables || this.tables.length === 0) {
            tableList.innerHTML = '<div class="no-tables">No tables found in this database</div>';
            return;
        }

        this.tables.forEach(table => {
            const tableItem = document.createElement('div');
            tableItem.className = 'table-item';
            tableItem.setAttribute('data-table-name', table.toLowerCase());
            tableItem.innerHTML = `
                <i class="fas fa-table"></i>
                <span>${table}</span>
            `;
            
            tableItem.addEventListener('click', () => {
                this.selectTable(table, tableItem);
            });

            tableList.appendChild(tableItem);
        });
    }
    
    filterTables(searchTerm) {
        const tableItems = document.querySelectorAll('.table-item');
        tableItems.forEach(item => {
            const tableName = item.getAttribute('data-table-name');
            if (tableName.includes(searchTerm)) {
                item.style.display = 'flex';
            } else {
                item.style.display = 'none';
            }
        });
    }

    selectTable(tableName, tableElement) {
        // Update active state
        document.querySelectorAll('.table-item').forEach(item => {
            item.classList.remove('active');
        });
        tableElement.classList.add('active');

        // Reset search and pagination
        this.currentTable = tableName;
        this.currentPage = 1;
        this.searchTerm = '';
        this.sortColumn = '';
        this.sortOrder = 'ASC';
        
        // Clear search input
        document.getElementById('search-input').value = '';

        // Show table viewer and hide welcome message
        document.getElementById('welcome-message').style.display = 'none';
        document.getElementById('table-viewer').style.display = 'flex';

        // Update table name
        document.getElementById('current-table-name').textContent = tableName;

        // Load table data
        this.loadTableData(this.currentDatabase, tableName);
    }

    async loadTableData(databaseId, tableName) {
        if (!databaseId || !tableName) return;

        const tableContainer = document.getElementById('table-container');
        const tableLoading = document.getElementById('table-loading');
        const dataTable = document.getElementById('data-table');
        const paginationContainer = document.getElementById('pagination-container');

        // Show loading state
        tableLoading.style.display = 'flex';
        dataTable.style.display = 'none';
        paginationContainer.style.display = 'none';

        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                per_page: this.perPage,
                sort_column: this.sortColumn,
                sort_order: this.sortOrder,
                search: this.searchTerm
            });

            this.searchColumns.forEach(col => {
                if (col !== 'all') {
                    params.append('search_columns', col);
                }
            });

            const response = await fetch(`/database/${encodeURIComponent(databaseId)}/table/${encodeURIComponent(tableName)}?${params}`);
            const result = await response.json();

            if (result.success) {
                this.lastPaginationInfo = result.pagination;
                this.renderTable(result);
                this.updateTableStats(result.pagination);
                this.renderPagination(result.pagination);
            } else {
                this.showToast('error', 'Load Failed', result.error || 'Failed to load table data');
            }
        } catch (error) {
            console.error('Load table error:', error);
            this.showToast('error', 'Load Failed', 'Network error occurred while loading table');
        } finally {
            tableLoading.style.display = 'none';
        }
    }

    renderTable(result) {
        const dataTable = document.getElementById('data-table');
        const tableHead = document.getElementById('table-head');
        const tableBody = document.getElementById('table-body');

        // Clear existing content
        tableHead.innerHTML = '';
        tableBody.innerHTML = '';

        if (result.data.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="100%" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                        <i class="fas fa-inbox" style="font-size: 2rem; margin-bottom: 1rem; display: block;"></i>
                        No data found
                    </td>
                </tr>
            `;
            dataTable.style.display = 'table';
            return;
        }

        // Create header row
        const headerRow = document.createElement('tr');
        result.columns.forEach(column => {
            const th = document.createElement('th');
            th.className = 'sortable';
            th.textContent = column.name;
            
            // Add sort classes
            if (this.sortColumn === column.name) {
                th.classList.add(this.sortOrder.toLowerCase() === 'asc' ? 'sort-asc' : 'sort-desc');
            }

            // Add click handler for sorting
            th.addEventListener('click', () => {
                this.sortTable(column.name);
            });

            headerRow.appendChild(th);
        });
        tableHead.appendChild(headerRow);

        // Create data rows
        result.data.forEach(row => {
            const tr = document.createElement('tr');
            result.columns.forEach(column => {
                const td = document.createElement('td');
                const value = row[column.name];
                td.innerHTML = this.formatCellValue(value, column.type) || '';
                td.title = this.getCellTooltip(value);
                tr.appendChild(td);
            });
            tableBody.appendChild(tr);
        });

        // Update search columns dropdown
        this.updateSearchColumns(result.columns);

        dataTable.style.display = 'table';
    }

    updateSearchColumns(columns) {
        const searchColumns = document.getElementById('search-columns');
        searchColumns.innerHTML = '<option value="all">All Columns</option>';
        
        columns.forEach(column => {
            const option = document.createElement('option');
            option.value = column.name;
            option.textContent = column.name;
            searchColumns.appendChild(option);
        });
    }

    updateTableStats(pagination) {
        const tableStats = document.getElementById('table-stats');
        const start = Math.min((pagination.page - 1) * pagination.per_page + 1, pagination.total);
        const end = Math.min(pagination.page * pagination.per_page, pagination.total);
        
        tableStats.textContent = `Showing ${start.toLocaleString()}-${end.toLocaleString()} of ${pagination.total.toLocaleString()} rows`;
    }

    renderPagination(pagination) {
        const paginationContainer = document.getElementById('pagination-container');
        const paginationInfo = document.getElementById('pagination-info');
        const paginationControls = document.getElementById('pagination-controls');

        // Update pagination info
        const start = Math.min((pagination.page - 1) * pagination.per_page + 1, pagination.total);
        const end = Math.min(pagination.page * pagination.per_page, pagination.total);
        paginationInfo.textContent = `Showing ${start.toLocaleString()}-${end.toLocaleString()} of ${pagination.total.toLocaleString()} entries`;

        // Clear existing controls
        paginationControls.innerHTML = '';

        // Previous button
        const prevBtn = document.createElement('button');
        prevBtn.className = 'pagination-btn';
        prevBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
        prevBtn.disabled = pagination.page <= 1;
        prevBtn.addEventListener('click', () => {
            if (pagination.page > 1) {
                this.currentPage = pagination.page - 1;
                this.loadTableData(this.currentDatabase, this.currentTable);
            }
        });
        paginationControls.appendChild(prevBtn);

        // Page numbers
        const totalPages = pagination.total_pages;
        const currentPage = pagination.page;
        const maxVisible = 5;

        let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
        let endPage = Math.min(totalPages, startPage + maxVisible - 1);

        if (endPage - startPage + 1 < maxVisible) {
            startPage = Math.max(1, endPage - maxVisible + 1);
        }

        // First page
        if (startPage > 1) {
            const firstBtn = this.createPageButton(1, currentPage);
            paginationControls.appendChild(firstBtn);
            
            if (startPage > 2) {
                const ellipsis = document.createElement('span');
                ellipsis.textContent = '...';
                ellipsis.className = 'pagination-ellipsis';
                ellipsis.style.padding = '0.5rem';
                ellipsis.style.color = 'var(--text-muted)';
                paginationControls.appendChild(ellipsis);
            }
        }

        // Visible pages
        for (let i = startPage; i <= endPage; i++) {
            const pageBtn = this.createPageButton(i, currentPage);
            paginationControls.appendChild(pageBtn);
        }

        // Last page
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const ellipsis = document.createElement('span');
                ellipsis.textContent = '...';
                ellipsis.className = 'pagination-ellipsis';
                ellipsis.style.padding = '0.5rem';
                ellipsis.style.color = 'var(--text-muted)';
                paginationControls.appendChild(ellipsis);
            }
            
            const lastBtn = this.createPageButton(totalPages, currentPage);
            paginationControls.appendChild(lastBtn);
        }

        // Next button
        const nextBtn = document.createElement('button');
        nextBtn.className = 'pagination-btn';
        nextBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
        nextBtn.disabled = pagination.page >= totalPages;
        nextBtn.addEventListener('click', () => {
            if (pagination.page < totalPages) {
                this.currentPage = pagination.page + 1;
                this.loadTableData(this.currentDatabase, this.currentTable);
            }
        });
        paginationControls.appendChild(nextBtn);

        paginationContainer.style.display = 'flex';
    }

    createPageButton(pageNum, currentPage) {
        const btn = document.createElement('button');
        btn.className = 'pagination-btn';
        btn.textContent = pageNum;
        
        if (pageNum === currentPage) {
            btn.classList.add('active');
        }
        
        btn.addEventListener('click', () => {
            this.currentPage = pageNum;
            this.loadTableData(this.currentDatabase, this.currentTable);
        });
        
        return btn;
    }

    sortTable(columnName) {
        if (this.sortColumn === columnName) {
            this.sortOrder = this.sortOrder === 'ASC' ? 'DESC' : 'ASC';
        } else {
            this.sortColumn = columnName;
            this.sortOrder = 'ASC';
        }
        
        this.currentPage = 1;
        this.loadTableData(this.currentDatabase, this.currentTable);
    }

    async exportTable() {
        if (!this.currentTable || !this.currentDatabase) return;

        this.showToast('info', 'Export Started', 'Preparing table data for export...');

        try {
            // Get all data without pagination
            const params = new URLSearchParams({
                page: 1,
                per_page: 50000, // Large number to get all data
                sort_column: this.sortColumn,
                sort_order: this.sortOrder,
                search: this.searchTerm
            });

            const response = await fetch(`/database/${encodeURIComponent(this.currentDatabase)}/table/${encodeURIComponent(this.currentTable)}?${params}`);
            const result = await response.json();

            if (result.success) {
                this.downloadCSV(result.data, result.columns, this.currentTable);
            } else {
                this.showToast('error', 'Export Failed', result.error || 'Failed to export table data');
            }
        } catch (error) {
            console.error('Export error:', error);
            this.showToast('error', 'Export Failed', 'Network error occurred during export');
        }
    }

    downloadCSV(data, columns, tableName) {
        // Create CSV content
        const headers = columns.map(col => col.name);
        const csvContent = [
            headers.join(','),
            ...data.map(row => 
                headers.map(header => {
                    const value = row[header] || '';
                    // Remove HTML tags and escape quotes
                    const cleanValue = value.toString().replace(/<[^>]*>/g, '').replace(/"/g, '""');
                    return `"${cleanValue}"`;
                }).join(',')
            )
        ].join('\n');

        // Create and trigger download
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        
        link.setAttribute('href', url);
        link.setAttribute('download', `${tableName}_export_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        this.showToast('success', 'Export Complete', `Table "${tableName}" exported successfully`);
    }

    showDatabaseActions() {
        const actionsElement = document.getElementById('database-actions');
        if (this.adminEnabled) {
            actionsElement.style.display = 'flex';
        } else {
            // Hide delete button if admin is not enabled
            actionsElement.style.display = 'none';
        }
    }
    
    hideDatabaseActions() {
        document.getElementById('database-actions').style.display = 'none';
    }
    
    async confirmDeleteDatabase() {
        if (!this.currentDatabase) return;
        
        if (!this.adminEnabled) {
            this.showToast('error', 'Action Disabled', 'Admin operations are disabled. Contact administrator.');
            return;
        }
        
        // Get admin token if not already set
        if (!this.adminToken) {
            this.adminToken = prompt('Enter admin token to perform this action:');
            if (!this.adminToken) {
                return; // User cancelled
            }
        }
        
        const dbInfo = this.databases.find(db => db.filename === this.currentDatabase);
        const confirmMessage = `Are you sure you want to delete "${dbInfo.original_name}"?\n\nThis action cannot be undone.`;
        
        if (!confirm(confirmMessage)) {
            return;
        }
        
        this.showLoadingOverlay('Deleting database...');
        
        try {
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
            const response = await fetch(`/database/${encodeURIComponent(this.currentDatabase)}/delete`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Admin-Token': this.adminToken
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showToast('success', 'Database Deleted', result.message);
                
                // Reload databases
                await this.loadDatabases();
                
                // Clear selection
                document.getElementById('database-select').value = '';
                this.clearDatabaseSelection();
                
                // If no databases left, show hero section
                if (this.databases.length === 0) {
                    this.showHeroSection();
                }
            } else {
                // If unauthorized, clear the admin token and show error
                if (response.status === 403) {
                    this.adminToken = null;
                    this.showToast('error', 'Authentication Failed', 'Invalid admin token. Please try again.');
                } else {
                    this.showToast('error', 'Delete Failed', result.error || 'Failed to delete database');
                }
            }
        } catch (error) {
            console.error('Delete error:', error);
            this.showToast('error', 'Delete Failed', 'Network error occurred during deletion');
        } finally {
            this.hideLoadingOverlay();
        }
    }
    
    showHelp() {
        const helpContent = `
            <div class="help-modal">
                <h3>How to Use Database Explorer</h3>
                <div class="help-section">
                    <h4>1. Upload Your Database</h4>
                    <p>Drag and drop or click to upload .mdb, .accdb, .sqlite, or .db files (max 100MB)</p>
                </div>
                <div class="help-section">
                    <h4>2. Browse Tables</h4>
                    <p>Select a database from the dropdown, then click on any table to view its data</p>
                </div>
                <div class="help-section">
                    <h4>3. Search & Filter</h4>
                    <p>Use the search bar to find specific data, or search within specific columns</p>
                </div>
                <div class="help-section">
                    <h4>4. Export Data</h4>
                    <p>Click the Export CSV button to download table data</p>
                </div>
                ${this.adminEnabled ? `
                <div class="help-section">
                    <h4>5. Admin Operations</h4>
                    <p>Delete databases using the delete button (requires admin token)</p>
                </div>
                ` : `
                <div class="help-section">
                    <h4>5. Admin Operations</h4>
                    <p>Admin operations are disabled on this server</p>
                </div>
                `}
            </div>
        `;
        
        this.showToast('info', 'Help & Documentation', helpContent);
    }
    
    showKeyboardShortcuts() {
        const shortcutsContent = `
            <div class="shortcuts-modal">
                <h3>Keyboard Shortcuts</h3>
                <div class="shortcuts-grid">
                    <div class="shortcut-item">
                        <kbd>Ctrl+U</kbd>
                        <span>Upload database file</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Ctrl+F</kbd>
                        <span>Focus search box</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Escape</kbd>
                        <span>Clear search</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Ctrl+←</kbd>
                        <span>Previous page</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Ctrl+→</kbd>
                        <span>Next page</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Ctrl+E</kbd>
                        <span>Export current table</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Ctrl+?</kbd>
                        <span>Show this help</span>
                    </div>
                </div>
            </div>
        `;
        
        this.showToast('info', 'Keyboard Shortcuts', shortcutsContent);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    formatCellValue(value, columnType) {
        if (value === null || value === undefined || value === '') {
            return '<span class="null-value">NULL</span>';
        }

        // Handle different data types
        const valueStr = String(value);
        
        // Date formatting
        if (this.isDateValue(valueStr)) {
            return this.formatDate(valueStr);
        }
        
        // Number formatting
        if (this.isNumericType(columnType) && this.isNumericValue(valueStr)) {
            return this.formatNumber(valueStr);
        }
        
        // Boolean formatting
        if (this.isBooleanValue(valueStr)) {
            return this.formatBoolean(valueStr);
        }
        
        // URL formatting
        if (this.isUrl(valueStr)) {
            return `<a href="${valueStr}" target="_blank" rel="noopener">${this.truncateText(valueStr, 50)}</a>`;
        }
        
        // Email formatting
        if (this.isEmail(valueStr)) {
            return `<a href="mailto:${valueStr}">${valueStr}</a>`;
        }
        
        // Truncate long text
        if (valueStr.length > 100) {
            return `<span class="truncated-text" title="${this.escapeHtml(valueStr)}">${this.escapeHtml(this.truncateText(valueStr, 100))}</span>`;
        }
        
        return this.escapeHtml(valueStr);
    }

    getCellTooltip(value) {
        if (value === null || value === undefined || value === '') {
            return 'NULL value';
        }
        const valueStr = String(value);
        return valueStr.length > 50 ? valueStr : '';
    }

    isDateValue(value) {
        // Check for common date patterns
        const datePatterns = [
            /^\d{4}-\d{2}-\d{2}/, // YYYY-MM-DD
            /^\d{2}\/\d{2}\/\d{4}/, // MM/DD/YYYY
            /^\d{2}-\d{2}-\d{4}/, // MM-DD-YYYY
            /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/ // ISO datetime
        ];
        
        return datePatterns.some(pattern => pattern.test(value)) && !isNaN(Date.parse(value));
    }

    formatDate(value) {
        try {
            const date = new Date(value);
            if (isNaN(date.getTime())) return value;
            
            // Check if it includes time
            if (value.includes('T') || value.includes(':')) {
                return `<span class="datetime-value">${date.toLocaleString()}</span>`;
            } else {
                return `<span class="date-value">${date.toLocaleDateString()}</span>`;
            }
        } catch (e) {
            return value;
        }
    }

    isNumericType(columnType) {
        const numericTypes = ['Number', 'Integer', 'Float', 'Double', 'Decimal', 'Currency', 'REAL', 'INTEGER', 'NUMERIC'];
        return numericTypes.includes(columnType);
    }

    isNumericValue(value) {
        return !isNaN(value) && !isNaN(parseFloat(value)) && isFinite(value);
    }

    formatNumber(value) {
        const num = parseFloat(value);
        if (Number.isInteger(num)) {
            return `<span class="number-value">${num.toLocaleString()}</span>`;
        } else {
            return `<span class="number-value">${num.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})}</span>`;
        }
    }

    isBooleanValue(value) {
        const booleanValues = ['true', 'false', '1', '0', 'yes', 'no', 'y', 'n'];
        return booleanValues.includes(value.toLowerCase());
    }

    formatBoolean(value) {
        const truthyValues = ['true', '1', 'yes', 'y'];
        const isTruthy = truthyValues.includes(value.toLowerCase());
        const icon = isTruthy ? 'fas fa-check-circle' : 'fas fa-times-circle';
        const className = isTruthy ? 'boolean-true' : 'boolean-false';
        return `<span class="boolean-value ${className}"><i class="${icon}"></i> ${isTruthy ? 'True' : 'False'}</span>`;
    }

    isUrl(value) {
        try {
            new URL(value);
            return value.startsWith('http://') || value.startsWith('https://');
        } catch {
            return false;
        }
    }

    isEmail(value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(value);
    }

    truncateText(text, length) {
        return text.length > length ? text.substring(0, length) + '...' : text;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showToast(type, title, message) {
        const toastContainer = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const iconMap = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };

        toast.innerHTML = `
            <i class="${iconMap[type]}"></i>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;

        toastContainer.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, 5000);
    }

    showLoadingOverlay(message = 'Loading...') {
        const overlay = document.getElementById('loading-overlay');
        const content = overlay.querySelector('.loading-content p');
        content.textContent = message;
        overlay.style.display = 'flex';
    }

    hideLoadingOverlay() {
        document.getElementById('loading-overlay').style.display = 'none';
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new DatabaseViewer();
});