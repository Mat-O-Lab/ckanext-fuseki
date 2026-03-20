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

      // Initialize Bootstrap tooltips
      var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
      tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
      });

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
            const haslogs = 'logs' in data.status;
            const hasgraph = 'graph' in data.status;
            if (hasgraph || haslogs) {
              self.el.find('button[name="delete"]').removeClass("invisible");
              self.el.find('a[name="query"]').removeClass("invisible");
              self.el.find('a[name="query"]').attr("href", data.status.queryurl);
              self.el.find('div[name="status"]').removeClass("invisible");
            };
            if (!haslogs) return;
            var length = Object.keys(data.status.logs).length;
            if (length) {
              if (length !== log_length) {
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
                log_length = length;
              }
            }
          },
          error: function (xhr, status, error) {
            // intentionally silent — status polling failures are non-critical
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
