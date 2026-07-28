<script>
  import { logs, calCursor, showToast, loading } from '../stores/appStore.js'
  
  let fileInput
  let uploadEl
  let isDragging = false
  
  // Format local Date to HH:MM (24h)
  function formatLocalHM(tsStr) {
    const d = new Date(tsStr)
    const h = String(d.getHours()).padStart(2, '0')
    const m = String(d.getMinutes()).padStart(2, '0')
    return `${h}:${m}`
  }
  
  // Get month name in Hebrew/English
  function getMonthName(date) {
    return date.toLocaleString('he-IL', { month: 'long', year: 'numeric' })
  }
  
  async function handleFileSelect(e) {
    const file = e.target.files?.[0]
    if (!file) return
    await processFile(file)
  }
  
  function handleDragOver(e) {
    e.preventDefault()
    isDragging = true
  }
  
  function handleDragLeave() {
    isDragging = false
  }
  
  async function handleDrop(e) {
    e.preventDefault()
    isDragging = false
    const file = e.dataTransfer?.files?.[0]
    if (file) {
      if (!file.name.toLowerCase().endsWith('.xls')) {
        showToast('נא להעלות קובץ XLS בלבד', 'error')
        return
      }
      await processFile(file)
    }
  }
  
  async function processFile(file) {
    loading.set(true)
    showToast('קורא את קובץ האקסל ומכין את הנתונים...', 'info')
    
    try {
      // 1. Get selected month from calendar cursor
      const targetYear = $calCursor.getFullYear()
      const targetMonth = $calCursor.getMonth() + 1
      const prefix = `${targetYear}-${String(targetMonth).padStart(2, '0')}`
      
      // 2. Filter home logs in memory
      // Sort logs by timestamp ascending
      const sortedLogs = [...$logs]
        .filter(l => l.platform === 'home' && l.date_key.startsWith(prefix))
        .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
      
      // Pair resume/pause events into intervals
      const homeIntervals = []
      const dayGroups = {}
      
      for (const log of sortedLogs) {
        if (!dayGroups[log.date_key]) dayGroups[log.date_key] = []
        dayGroups[log.date_key].push(log)
      }
      
      for (const [dateKey, dayLogs] of Object.entries(dayGroups)) {
        let openResume = null
        for (const log of dayLogs) {
          if (log.action === 'resume') {
            openResume = log
          } else if (log.action === 'pause' && openResume) {
            homeIntervals.push({
              date: dateKey,
              start: formatLocalHM(openResume.timestamp),
              end: formatLocalHM(log.timestamp)
            })
            openResume = null
          }
        }
      }
      
      // 3. Read file as ArrayBuffer and convert to Base64
      const reader = new FileReader()
      reader.onload = async (event) => {
        try {
          const arrayBuffer = event.target.result
          const bytes = new Uint8Array(arrayBuffer)
          let binary = ''
          for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i])
          }
          const base64 = btoa(binary)
          
          // 4. Send to Vite backend merge endpoint
          // In production/GitHub Pages, this API is missing, so we handle fetch failures gracefully.
          const res = await fetch('/api/merge-xls', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              xlsBase64: base64,
              logs: homeIntervals
            })
          })
          
          if (!res.ok) {
            let errMsg = 'שגיאת שרת לא ידועה'
            try {
              const errJson = await res.json()
              errMsg = errJson.error || errMsg
            } catch {}
            throw new Error(errMsg)
          }
          
          // 5. Trigger download of the merged file
          const blob = await res.blob()
          const downloadUrl = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = downloadUrl
          
          // Formulate clean name e.g. merged_july_2026.xls
          const origName = file.name.replace(/\.xls$/i, '')
          a.download = `${origName}_מעודכן.xls`
          a.click()
          URL.revokeObjectURL(downloadUrl)
          
          showToast('הקובץ מוזג ועודכן בהצלחה!', 'success')
        } catch (err) {
          console.error(err)
          showToast(`מיזוג נכשל: ${err.message}`, 'error')
        } finally {
          loading.set(false)
          if (fileInput) fileInput.value = ''
        }
      }
      
      reader.readAsArrayBuffer(file)
      
    } catch (err) {
      console.error(err)
      showToast('עיבוד הקובץ נכשל: ' + err.message, 'error')
      loading.set(false)
      if (fileInput) fileInput.value = ''
    }
  }
</script>

<div class="card xls-merge-card">
  <div class="header-row">
    <div class="title-group">
      <span class="icon">📊</span>
      <h3>עדכון ומיזוג קובץ אקסל רשמי</h3>
    </div>
    <span class="pill pill-home tabnum">חודש נבחר: {getMonthName($calCursor)}</span>
  </div>
  
  <p class="description">
    העלה את דוח השעות הרשמי שקיבלת מהחברה (בפורמט <code>.xls</code>). המערכת תשלב לתוכו אוטומטית את שעות העבודה מהבית המדווחות באפליקציה ותחשב מחדש את כל התקנים והשעות הנוספות מבלי לפגוע בעיצוב ובמבנה הדוח המקורי.
  </p>
  
  <!-- Drag & Drop Dropzone -->
  <button 
    type="button"
    class="dropzone"
    class:dragging={isDragging}
    on:dragover={handleDragOver}
    on:dragleave={handleDragLeave}
    on:drop={handleDrop}
    on:click={() => fileInput.click()}
  >
    <div class="dropzone-content">
      <span class="upload-icon">📥</span>
      <span class="primary-text">לחץ לבחירת קובץ או גרור לכאן קובץ אקסל (.xls)</span>
      <span class="secondary-text">תומך בדוחות של JBClock</span>
    </div>
  </button>
  
  <input 
    type="file" 
    accept=".xls" 
    bind:this={fileInput} 
    on:change={handleFileSelect} 
    style="display: none;" 
  />
  
  <div class="info-alert">
    <span class="alert-icon">💡</span>
    <p>שעות העבודה מהבית ימוזגו לתוך עמודות הכניסה/יציאה המשניות (כניסה 2 ויציאה 2) בהתאמה לכל יום עבודה.</p>
  </div>
</div>

<style>
  .xls-merge-card {
    border-top: 4px solid var(--color-home);
    direction: rtl;
  }
  
  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-3);
  }
  
  .title-group {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  
  .title-group h3 {
    font-size: 1.1rem;
    font-weight: 600;
  }
  
  .icon {
    font-size: 1.3rem;
  }
  
  .description {
    font-size: 0.875rem;
    color: var(--color-text-muted);
    line-height: 1.5;
    margin-bottom: var(--space-4);
  }
  
  .dropzone {
    width: 100%;
    border: 2px dashed var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-6) var(--space-4);
    background: var(--color-surface-2);
    transition: border-color var(--transition), background var(--transition), transform var(--transition);
    outline: none;
    text-align: center;
    margin-bottom: var(--space-4);
  }
  
  .dropzone:hover, .dropzone.dragging {
    border-color: var(--color-home);
    background: var(--color-home-subtle);
  }
  
  .dropzone:active {
    transform: scale(0.995);
  }
  
  .dropzone-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
  }
  
  .upload-icon {
    font-size: 2.2rem;
    filter: grayscale(0.2);
  }
  
  .primary-text {
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--color-text);
  }
  
  .secondary-text {
    font-size: 0.8125rem;
    color: var(--color-text-muted);
  }
  
  .info-alert {
    display: flex;
    gap: var(--space-2);
    padding: var(--space-3);
    background: var(--color-surface-2);
    border-radius: var(--radius-sm);
    border-right: 3px solid var(--color-text-muted);
  }
  
  .alert-icon {
    font-size: 1rem;
  }
  
  .info-alert p {
    font-size: 0.8125rem;
    color: var(--color-text-muted);
    line-height: 1.4;
  }
</style>
