document.addEventListener('DOMContentLoaded', function() {
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            fetchAndUpdateStatus();
            loadParkingRecommendations();
        });
    }
    
    const processFrameBtn = document.getElementById('processFrameBtn');
    if (processFrameBtn) {
        processFrameBtn.addEventListener('click', function() {
            fetch('/api/process_frame')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Frame processed successfully');
                        fetchAndUpdateStatus();
                        loadParkingRecommendations();
                    } else {
                        alert('Error processing frame: ' + data.message);
                    }
                })
                .catch(error => console.error('Error processing frame:', error));
        });
    }
    
    // Load recommendations on page load
    loadParkingRecommendations();
    
    // Auto-refresh parking status and recommendations every 5 seconds
    const autoRefreshPaths = ['/parking_status', '/dashboard', '/admin'];
    const currentPath = window.location.pathname;
    
    if (autoRefreshPaths.some(path => currentPath.includes(path))) {
        // Initial fetch
        fetchAndUpdateStatus();
        loadParkingRecommendations();
        
        // Set up auto-refresh
        setInterval(function() {
            fetchAndUpdateStatus();
            loadParkingRecommendations();
        }, 5000);
    }
    
    // Event delegation for dynamically added buttons
    document.body.addEventListener('click', function(event) {
        const target = event.target.closest('.toggle-space');
        if (target) {
            const spaceId = target.getAttribute('data-space-id');
            alert(`Would toggle space ${spaceId} status (API endpoint not implemented)`);
        }
        
        const makeAdminBtn = event.target.closest('.make-admin');
        if(makeAdminBtn) {
            const userId = makeAdminBtn.getAttribute('data-user-id');
            alert(`Would make user ${userId} an admin (API endpoint not implemented)`);
        }

        const deleteUserBtn = event.target.closest('.delete-user');
        if(deleteUserBtn) {
            const userId = deleteUserBtn.getAttribute('data-user-id');
            if (confirm('Are you sure you want to delete this user?')) {
                alert(`Would delete user ${userId} (API endpoint not implemented)`);
            }
        }
    });
});

function loadParkingRecommendations() {
    fetch('/api/parking_recommendations')
        .then(response => response.json())
        .then(data => {
            updateParkingGuidanceUI(data);
        })
        .catch(error => {
            console.error('Error loading recommendations:', error);
        });
}

function updateParkingGuidanceUI(data) {
    const bestSpotText = document.getElementById('bestSpotText');
    const availableCountElement = document.getElementById('availableCount');
    
    if (data.available) {
        if (availableCountElement) {
            availableCountElement.textContent = data.total_available;
        }
        
        if (data.best_spots && data.best_spots.length > 0) {
            bestSpotText.innerHTML = `<i class="bi bi-star-fill"></i> Best: Space ${data.best_spots[0]}`;
            bestSpotText.className = 'badge bg-warning text-dark fs-6';
            
            // Highlight recommended spots in the table
            data.best_spots.forEach((spotId, index) => {
                const recCell = document.getElementById(`rec-${spotId}`);
                if (recCell) {
                    if (index === 0) {
                        recCell.innerHTML = '<span class="badge bg-warning text-dark"><i class="bi bi-star-fill"></i> BEST</span>';
                    } else {
                        recCell.innerHTML = '<span class="badge bg-info text-white">GOOD</span>';
                    }
                }
            });
        }
    } else {
        bestSpotText.textContent = 'No spaces available';
        bestSpotText.className = 'badge bg-danger fs-6';
    }
}

function fetchAndUpdateStatus() {
    // Show loading spinner
    const loadingSpinner = document.getElementById('loadingSpinner');
    if (loadingSpinner) {
        loadingSpinner.classList.remove('d-none');
    }
    
    fetch('/api/parking_status')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            updateParkingStatusUI(data);
        })
        .catch(error => {
            console.error('Error fetching parking status:', error);
        })
        .finally(() => {
            // Hide loading spinner
            if (loadingSpinner) {
                loadingSpinner.classList.add('d-none');
            }
        });
}

function updateParkingStatusUI(data) {
    console.log('Received data:', data);
    
    // Update the parking spaces grid
    const parkingSpacesContainer = document.getElementById('parkingSpaces');
    if (parkingSpacesContainer) {
        parkingSpacesContainer.innerHTML = '';
        
        data.forEach(space => {
            const slot = document.createElement('div');
            const isOccupied = space.occupied;
            const spaceId = space.id;
            
            if (isOccupied) {
                slot.className = 'parking-slot occupied';
                slot.title = `Space ${spaceId} - Occupied`;
                slot.innerHTML = `
                    <div class="slot-icon"><i class="bi bi-car-front-fill"></i></div>
                    <span class="slot-id">${spaceId}</span>
                `;
            } else {
                slot.className = 'parking-slot available';
                slot.title = `Space ${spaceId} - Available`;
                slot.innerHTML = `
                    <span class="slot-id">SLOT</span>
                    <span>${spaceId}</span>
                `;
            }
            parkingSpacesContainer.appendChild(slot);
        });
    }
    
    // Update the statistics cards
    const availableCount = data.filter(space => !space.occupied).length;
    const occupiedCount = data.length - availableCount;
    const totalCount = data.length;
    const utilizationRate = totalCount > 0 ? (occupiedCount / totalCount * 100).toFixed(1) : 0;
    
    // Update all count elements
    const availableElement = document.getElementById('availableCountCard');
    const occupiedElement = document.getElementById('occupiedCount');
    const totalElement = document.getElementById('totalCount');
    const utilizationElement = document.getElementById('utilizationRate');
    
    if (availableElement) availableElement.textContent = availableCount;
    if (occupiedElement) occupiedElement.textContent = occupiedCount;
    if (totalElement) totalElement.textContent = totalCount;
    if (utilizationElement) utilizationElement.textContent = `${utilizationRate}%`;
}

// Function for parking_status.html quick guide
function loadQuickGuide() {
    loadParkingRecommendations();
    fetchAndUpdateStatus();
}