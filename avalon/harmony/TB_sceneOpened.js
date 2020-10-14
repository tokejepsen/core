/** class implementing avalon client. **/
function Client() {
  var self = this;
  /** socket */
  self.socket = new QTcpSocket(this);
  /** receiving data buffer */
  self.received = "";
  /** lock */
  self.lock = 1;

  /**
   * Log message in debug level.
   * @param {string} data - message
   */
  self.log_debug = function(data) {
      message = typeof(data.message) != "undefined" ? data.message : data;
      MessageLog.trace("(DEBUG): " + message.toString());
  };

  /**
   * Log message in info level.
   * @param {string} data - message
   */
  self.log_info = function(data) {
      message = typeof(data.message) != "undefined" ? data.message : data;
      MessageLog.trace("(INFO): " + message.toString());
  };

  /**
   * Log message in warning level.
   * @param {string} data - message
   */
  self.log_warning = function(data) {
      message = typeof(data.message) != "undefined" ? data.message : data;
      MessageLog.trace("(WARNING): " + message.toString());
  };

  /**
   * Log message in error level.
   * @param {string} data - message
   */
  self.log_error = function(data) {
      message = typeof(data.message) != "undefined" ? data.message : data;
      MessageLog.trace("(ERROR): " + message.toString());
  };

  /**
   * Show message in Harmony GUI as popup window.
   * @param {string} msg - message
   */
  self.show_message = function(msg) {
    MessageBox.information(msg);
  };

  /**
   * Process recieved request. This will eval recieved function and produce
   * results.
   * @param {object} request - recieved request JSON
   * @return {object} result of evaled function.
   */
  self.process_request = function(request) {
    self.log_debug("Processing: " + JSON.stringify(request));
    var result = null;

    if (request["function"] != null) {
      try {
        var _func = eval.call( null, request["function"]);

        if (request.args == null) {
          result = _func();
        } else {
          result = _func(request.args);
        }
      } catch (error) {
        result = "Error processing request.\n" +
                 "Request:\n" +
                 JSON.stringify(request) + "\n" +
                 "Error:\n" + error;
      }
    }
    return result;
  };

  /**
   * Executed when receiving data to socket.
   */
  self.on_ready_read = function() {
    self.log_debug("Receiving data ...");
    self.log_debug("Locking ...");
    self.lock = 1;
    data = self.socket.readAll();

    if (data.size() != 0) {
      for ( var i = 0; i < data.size(); ++i) {
        self.received = self.received.concat(String.fromCharCode(data.at(i)));
      }
    }
    self.log_debug("Received: " + self.received);

    request = JSON.parse(self.received);

    self.log_debug("Request: " + JSON.stringify(request));

    request.result = self.process_request(request);
    if (!request.reply) {
      request.reply = true;
      self._send(JSON.stringify(request));
    }

    self.received = "";
    self.log_debug("Unlocking ...");
    self.lock = 0;
  };

  /**
   * Executed when connected to server.
   */
  self.on_connected = function() {
    self.log_debug("Connected to server ...");
    self.lock = 0;
    self.socket.readyRead.connect(self.on_ready_read);

    var app = QCoreApplication.instance();

    app.avalon_client.send({
        "module": "avalon.api",
        "method": "emit",
        "args": ["application.launched"]
      }, false);
  };

  self._send = function(message) {
    self.log_debug("Sending: " + message);

    var data = new QByteArray();
    outstr = new QDataStream(data, QIODevice.WriteOnly);
    outstr.writeInt(0);
    data.append("UTF-8");
    outstr.device().seek(0);
    outstr.writeInt(data.size() - 4);
    var codec = QTextCodec.codecForUtfText(data);
    self.socket.write(codec.fromUnicode(message));
  };

  /**
   * Timer to block until lock is released.
   */
  self.waitForLock = function() {
    if (self.lock == 0) {
      self.log_debug("Unlocked ...");
      return;
    } else {
      setTimeout(self.waitForLock, 300);
    }
  };

  /**
   * Send request to server.
   * @param {object} request - json encoded request.
   * @param {bool} wait - wait for reply.
   */
  self.send = function(request, wait) {
    if (self.lock !== 0) {
      self.log_debug("Still locked, waiting for unlock ...");
      self.waitForLock();
    }

    self._send(JSON.stringify(request));

    // buffer self.recieved is cleared by on_ready_read()
    // Nothing except it should modify this buffer.
    while (wait) {
      try {
        JSON.parse(self.received);
        break;
      } catch(err) {
        self.socket.waitForReadyRead(5000);
      }
    }
  };

  /**
   * Executed on disconnection.
   */
  self.on_disconnected = function()
  {
    self.socket.close();
  };

  /**
   * Disconnect from server.
   */
  self.disconnect = function()
  {
    self.socket.close();
  };

  self.socket.connected.connect(self.on_connected);
  self.socket.disconnected.connect(self.on_disconnected);
}

/**
 * Entry point, creating Avalon Client.
 */
function start() {
  var self = this;
  /** hostname or ip of server - should be localhost */
  var host = "127.0.0.1";
  /** port of the server */
  var port = parseInt(System.getenv("AVALON_HARMONY_PORT"));

  // Attach the client to the QApplication to preserve.
  var app = QCoreApplication.instance();

  if (app.avalon_client == null) {
    app.avalon_client = new Client();
    app.avalon_client.socket.connectToHost(host, port);
  }

	var menu_bar = QApplication.activeWindow().menuBar();
	var actions = menu_bar.actions();
	app.avalon_menu = null;

	for (var i = 0 ; i < actions.length; i++) {
    if (actions[i].text == "Avalon") {
      app.avalon_menu = true;
    }
  }

  var menu = null;
	if (app.avalon_menu == null) {
    var menu = menu_bar.addMenu("Avalon");
  }

  /**
   * Show creator
   */
  self.on_creator = function() {
    app.avalon_client.send({
        "module": "avalon.harmony.lib",
        "method": "show",
        "args": ["avalon.tools.creator"]
      }, false);
  };
  // Add creator item to menu
	if (app.avalon_menu == null) {
    var action = menu.addAction("Create...");
    action.triggered.connect(self.on_creator);
	}

  /**
   * Show Workfiles
   */
  self.on_workfiles = function() {
    app.avalon_client.send({
        "module": "avalon.harmony.lib",
        "method": "show",
        "args": ["avalon.tools.workfiles"]
      }, false);
  };
  // Add workfiles item to menu
	if (app.avalon_menu == null)
	{
    action = menu.addAction("Workfiles");
    action.triggered.connect(self.on_workfiles);
	}

  /**
   * Show Loader
   */
  self.on_load = function() {
    app.avalon_client.send({
          "module": "avalon.harmony.lib",
          "method": "show",
          "args": ["avalon.tools.loader"]
        }, false);
  };
  // add Loader item to menu
	if (app.avalon_menu == null) {
    action = menu.addAction("Load...");
    action.triggered.connect(self.on_load);
	}

  /**
   * Show Publisher
   */
  self.on_publish = function() {
    app.avalon_client.send({
          "module": "avalon.harmony.lib",
          "method": "show",
          "args": ["avalon.tools.publish"]
        }, false);
  };
  // add Publisher item to menu
	if (app.avalon_menu == null)
	{
    action = menu.addAction("Publish...");
    action.triggered.connect(self.on_publish);
	}

  /**
   * Show Scene Manager
   */
  self.on_manage = function() {
    app.avalon_client.send({
          "module": "avalon.harmony.lib",
          "method": "show",
          "args": ["avalon.tools.sceneinventory"]
        }, false);
  };
  // add Scene Manager item to menu
	if (app.avalon_menu == null)
	{
    action = menu.addAction("Manage...");
    action.triggered.connect(self.on_manage);
	}

  // FIXME(antirotor): We need to disable `on_file_changed` now as is wreak
  // havoc when "Save" is called multiple times and zipping didn't finished yet
  /*

  // Watch scene file for changes.
  app.on_file_changed = function(path)
  {
    var app = QCoreApplication.instance();
    if (app.avalon_on_file_changed){
      app.avalon_client.send(
        {
          "module": "avalon.harmony.lib",
          "method": "on_file_changed",
          "args": [path]
        },
        false
      );
    }

    app.watcher.addPath(path);
  };


	app.watcher = new QFileSystemWatcher();
	scene_path = scene.currentProjectPath() +"/" + scene.currentVersionName() + ".xstage";
	app.watcher.addPath(scene_path);
	app.watcher.fileChanged.connect(app.on_file_changed);
  app.avalon_on_file_changed = true;
  */
  app.on_file_changed = function(path) {
    // empty stub
  };
}

function ensureSceneSettings() {
  var app = QCoreApplication.instance();
  app.avalon_client.send(
    {
      "module": "pype.hosts.harmony",
      "method": "ensure_scene_settings",
      "args": []
    },
    false
  );
}

function TB_sceneOpened()
{
  start();
}
