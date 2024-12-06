ckan.module('fuseki', function (jQuery) {
  return {
    options: {
      parameters: {
        html: {
          contentType: 'application/json', // change the content type to text/html
          dataType: 'json', // change the data type to html
          dataConverter: function (data) { return data; },
          language: 'json'
        }
      }
    },
    initialize: function () {
      var self = this;
      var p;
      p = this.options.parameters.html;
      console.log("Initialized Fuseki for element: ", this.el);
      var log_length;
      log_length = 0;
      var update = function () { // define the update function
        jQuery.ajax({
          url: "fuseki/status",
          type: 'GET',
          contentType: p.contentType,
          dataType: p.dataType,
          data: { get_param: 'value' },
          success: function (data) {
            console.log(data);
            // console.log(log_length, length);
            const haslogs = 'logs' in data.status;
            const hasgraph = 'graph' in data.status;
             if (hasresults || haslogs) {
              console.log(self.el.find('button[name="delete"]'));
              self.el.find('button[name="delete"]').removeClass("invisible");
              self.el.find('a[name="query"]').removeClass("invisible");
              self.el.find('a[name="query"]').attr("href", data.status.queryurl);
              self.el.find('div[name="status"]').removeClass("invisible");
            };
            console.log(haslogs, hasgraph);
            if (!haslogs) return;
            var length = Object.keys(data.status.logs).length;
            if (length) {
              if (length !== log_length) {
                // self.el.html(JSON.stringify(data, null, 2)); // update the HTML if there are changes
                console.log(data.status.logs)
                var logs_div = $(self.el).find('ul[name="log"]');
                jQuery.each(data.status.logs, function (key, value) {
                  if (key + 1 < log_length) return;
                  logs_div.append("<li class='item "
                    + value.class +
                    "'><i class='fa icon fa-"
                    + value.icon +
                    "'></i><div class='alert alert-"
                    + value.alertlevel +
                    " mb-0 mt-3' role='alert'>"
                    + value.message +
                    "</div><span class='date' title='timestamp'>"
                    + value.timestamp +
                    "</span></li>");
                });
                console.log("Fuseki: status updated");
                log_length = length;
              }
            } else {
              console.log('Error: #ajax-status element not found');
            }
          },
          error: function (xhr, status, error) {
            console.log('Error:', error);
          },
          complete: function () {
            // call the update function recursively after a delay
            setTimeout(update, 2000);
          },

        });
        jQuery('#check-reasoning').change(function () {
          jQuery('#reasoner').prop('disabled', !this.checked);
        });
      };
      update(); // call the update function immediately after initialization
    }
  };
});
