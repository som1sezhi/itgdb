'use strict';

class ProgressBarController {
  constructor(url) {
    this.progressBars = {};
    this.url = (location.protocol === 'https:' ? 'wss' : 'ws')
      + '://' + window.location.host + url;
  }

  register(taskId, progressBar) {
    this.progressBars[taskId] = progressBar;
  }

  start() {
    const socket = new WebSocket(this.url);

    socket.onopen = (e) => {
      // send array of task IDs to listen to
      socket.send(JSON.stringify(Object.keys(this.progressBars)));
    }

    socket.onmessage = (e) => {
      const data = JSON.parse(e.data);
      for (const barData of data)
        this.progressBars[barData.id].update(barData);
    };

    socket.onclose = (e) => {
      console.error('Socket closed unexpectedly');
    };
  }
}


class ProgressBar {
  constructor(options) {
    this.barElem = options.barElem;
    this.barMessageElem = options.barMessageElem;

    this.barElem.style.width = '0%';
    this.barElem.style.backgroundColor = '#3280cf';
    this.barMessageElem.textContent = 'Waiting...';
  }

  update(data) {
    if (data.state === 'PENDING')
      return;
    
    if (data.state === 'SUCCESS') {
      this.barElem.style.backgroundColor = '#2cd459';
    } else if (data.state === 'FAILURE') {
      this.barElem.style.backgroundColor = '#e80f28';
    }

    this.barElem.style.width = `${data.progress * 100}%`;
    this.barMessageElem.textContent = data.message;
  }
}