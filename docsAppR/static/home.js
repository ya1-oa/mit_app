//in the future convert this project to make a unique url for each folder

let dict = JSON.parse(document.getElementById('file-list').textContent)

function clickedFileName(fileClass){
    let fileName = document.getElementsByClassName(fileClass).textContent
    console.log(fileName)
    return fileName
}
function searchJsonForFile(filesObj, fileName){
    if (typeof filesObj !== "object" || filesObj === null) {
        console.log(filesObj === fileName ? filesObj : undefined)
        return filesObj === fileName ? filesObj : undefined; 
    }
    return filesObj[fileName]
}   

function clearTable() {
    let fileTable = document.getElementById("table-1")
    let rows = fileTable.rows, rowcount = rows.length, r;

    for (r=rowcount-1; r>0; r--){
        fileTable.deleteRow(r)
    }
}

function showContents(fileInJson) {
    const table = document.getElementById("table-1")
    max = Object.keys(fileInJson).length

    for (const [key, value] of Object.entries(fileInJson)){
            let tr = document.createElement('tr')
            table.appendChild(tr)
            let td = document.createElement('td')
            tr.appendChild(td)
            td.appendChild(document.createTextNode(key))
            td.setAttribute("onclick", "updateTable(this," + JSON.stringify(fileInJson) + ")")
        }
}

function createTable() {
    const card = document.getElementsByClassName("card-body")[0]
    let filesTable = document.createElement('table')
    let tableHead = document.createElement('thead')
    let tableBody = document.createElement('tbody')
    let tableRow = document.createElement('tr')
    
    filesTable.appendChild(tableHead)
    filesTable.appendChild(tableBody)
    filesTable.classList.add('table')
    filesTable.setAttribute("id", "table-1")
    tableHead.appendChild(tableRow)

    const headers = ['Type', 'Name', 'Created', 'Edited', 'Size']
    for (let i = 0; i < headers.length; i++) {
        let tableHeader = document.createElement('th')
        let txt = document.createTextNode(headers[i])
        tableRow.appendChild(tableHeader)
        tableHeader.appendChild(txt)
    }

    for (const [key, value] of Object.entries(dict)){
        let newRow = document.createElement('tr')
        let newData = document.createElement('td')
        let txt = document.createTextNode(key)
        tableBody.appendChild(newRow)
        newRow.appendChild(newData)
        newData.appendChild(txt)
        newData.setAttribute("onclick", "updateTable(this, dict)")
    }

    card.appendChild(filesTable)
}

function showPathToFile(fileName) {
    const breadcrumb = document.getElementById("ordered-list")
    let li = document.createElement('li')
    let txt = document.createTextNode(fileName)
    breadcrumb.appendChild(li)
    li.classList.add('breadcrumb-item')
    li.appendChild(txt)
}

function updateTable(elementObj, dictObj) {
    //check if element clicked is a normal string or a filename (.xlsx .pdf  etc) do two different things to each
    const fileName = elementObj.textContent
    const fileValInJson = searchJsonForFile(dictObj, fileName)
   
    if (typeof fileValInJson === 'string' || fileValInJson instanceof String) {
        // code for opening a file based on filetype
        
    }
    else {
        clearTable()
        showContents(fileValInJson)
        showPathToFile(fileName)
    }
    
}

createTable()                   