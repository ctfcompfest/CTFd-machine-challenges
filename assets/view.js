var htmlLoading = `<span class="spinner-border spinner-border-sm mr-1" role="status"></span>Processing...`

function setMachineTimer(time_end) {
    let timer = setInterval(updateExpires, 300, time_end)
    window.sessionStorage.setItem('machineTimerID', timer)
}

function clearMachineTimer() {
    let timer = parseInt(window.sessionStorage.getItem('machineTimerID'))
    clearInterval(timer)
}

function updateButton(id, show, attr, html = undefined) {
    if (attr !== undefined) {
        for (const [key, value] of Object.entries(attr)) {
            CTFd.lib.$(id).attr(key, value)
        }
    }
    if (html !== undefined)
        CTFd.lib.$(id).html(html)
    if (show === true) CTFd.lib.$(id).show()
    else CTFd.lib.$(id).hide()
}

function updateExpires(e) {
    let s = Math.floor(Date.now() / 1000)
    let v = e - s
    let timeLbl = ''
    if (v <= 0) {
        timeLbl = '-'
        clearMachineTimer()
        CTFd._internal.challenge.machineTerminate()
    } else {
        let h = parseInt(v / 3600)
        if (h > 0) timeLbl += `${h}h `

        let m = parseInt((v % 3600) / 60)
        if (m > 0) timeLbl += `${m}m `

        let s = v % 60
        if (s > 0) timeLbl += `${s}s `
    }
    CTFd.lib.$('#machine-expires p').html(timeLbl)
}

CTFd._internal.challenge.data = undefined

CTFd._internal.challenge.renderer = CTFd.lib.markdown()


CTFd._internal.challenge.preRender = function () { }

CTFd._internal.challenge.render = function (markdown) {
    return CTFd._internal.challenge.renderer.render(markdown)
}

CTFd._internal.challenge.postRender = function () {
    clearMachineTimer()
    updateButton('#machine-start', true, {'disabled': true}, htmlLoading)
    CTFd._internal.challenge.machineStatus(true)

    var jQuery = CTFd.lib.$
    jQuery('#machine-start').click(function() {
        CTFd._internal.challenge.machineStart()
    })
    jQuery('#machine-terminate').click(function() {
        CTFd._internal.challenge.machineTerminate()
    })
}


CTFd._internal.challenge.submit = function (preview) {
    var challenge_id = parseInt(CTFd.lib.$('#challenge-id').val())
    var submission = CTFd.lib.$('#challenge-input').val()

    var body = {
        'challenge_id': challenge_id,
        'submission': submission,
    }
    var params = {}
    if (preview) {
        params['preview'] = true
    }

    return CTFd.api.post_challenge_attempt(params, body).then(function (response) {
        if (response.status === 429) {
            // User was ratelimited but process response
            return response
        }
        if (response.status === 403) {
            // User is not logged in or CTF is paused.
            return response
        }
        return response
    })
}

function fetchMachineAPI(method, path, body) {
    let url = CTFd.api.domain + '/machines' + path
    if (body === undefined) {
        body = {}
    }
    let headers = {
        'Accept': 'application/json',
        'CSRF-Token': CTFd.config.csrfNonce
    }
    
    if (method == 'GET') {
        return CTFd.lib.$.ajax(url, {
            method: method,
            data: body,
            headers: headers
        })    
    }

    return CTFd.lib.$.ajax(url, {
        method: method,
        data: JSON.stringify(body),
        contentType: 'application/json',
        headers: headers
    })
}

CTFd._internal.challenge.machineStart = function () {
    updateButton('#machine-start', true, {'disabled': true}, htmlLoading)
    let challenge_id = parseInt(CTFd.lib.$('#challenge-id').val())
    let body = {
        'challenge_id': challenge_id
    }
    fetchMachineAPI('POST', '', body)
        .then((data) => {
            setTimeout(
                CTFd._internal.challenge.machineStatus,
                5000
            )
        })
        .fail((xhr) => {
            let errors = xhr.responseJSON
            CTFd.ui.ezq.ezAlert({
                title: 'Failed',
                body: errors['errors'] || 'Failed to process your request.',
                button: 'Close'
            })
            updateButton('#machine-start', true, {'disabled': false}, 'Deploy')
        })
}

CTFd._internal.challenge.machineStatus = function (check = false) {
    let path = "/" + CTFd.lib.$('#challenge-id').val()
    fetchMachineAPI('GET', path)
        .then((data) => {
            if (data.success == false) {
                updateButton('#machine-start', true, {'disabled': false}, 'Deploy')
                return;
            }
            
            data = data.data
            
            let machineDetail = JSON.parse(data.detail)
            if (machineDetail['lastStatus'] === 'RUNNING') {
                let timeEnd = Math.floor(Date.parse(data.time_end) / 1000)
                setMachineTimer(timeEnd)

                CTFd.lib.$('#machine-detail').empty()

                if (machineDetail['containers'].length == 0) {
                    CTFd.lib.$('#machine-detail').append("<p>" + machineDetail['publicIp'] + "</p>")
                } else {
                    let containerHtml = '<div>';
                    for (let container of machineDetail['containers']) {
                        let html = `[${container['name']}]`
                        for (let port of container['portMappings']) {
                            html += `<br>${machineDetail['publicIp']}:${port['hostPort']}`
                        }
                        containerHtml += "<p>" + html + "</p>"
                    }
                    containerHtml += "</div>"
                    CTFd.lib.$('#machine-detail').append(containerHtml)
                }

                updateButton('#machine-start', false, {'disabled': true})
                updateButton('#machine-terminate', true, {'disabled': false}, 'Terminate')
            } else {
                setTimeout(CTFd._internal.challenge.machineStatus, 5000)
            }
        })
        .fail((xhr) => {
            updateButton('#machine-start', true, {'disabled': false}, 'Deploy')
            if (check) return;
            
            CTFd.ui.ezq.ezAlert({
                title: 'Failed',
                body: 'Failed to update machine status. Please ask the administrator.',
                button: 'Close'
            })
        })
}

CTFd._internal.challenge.machineTerminate = function () {
    updateButton('#machine-terminate', true, {'disabled': true}, htmlLoading)
    var path ="/" + CTFd.lib.$('#challenge-id').val()
    fetchMachineAPI('DELETE', path)
        .then((data) => {
            clearMachineTimer()
            CTFd.lib.$('#machine-detail').empty()
            CTFd.lib.$('#machine-detail').append('<p>-</p>')
            
            CTFd.lib.$('#machine-expires').empty()
            CTFd.lib.$('#machine-expires').append('<p>-</p>')
            
            updateButton('#machine-terminate', false, {'disabled': true})
            updateButton('#machine-start', true, {'disabled': false}, 'Deploy')
        })
        .fail((xhr) => {
            CTFd.ui.ezq.ezAlert({
                title: 'Failed',
                body: 'Failed to terminate machine.',
                button: 'Close'
            })
            updateButton('#machine-terminate', true, {'disabled': false}, 'Terminate')
        })
}