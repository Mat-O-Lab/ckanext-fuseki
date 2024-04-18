ckan.module('fuseki', function (jQuery) {
  return {
    options: {
      parameters: {
        html: {
          contentType: 'text/html', // change the content type to text/html
          dataType: 'html', // change the data type to html
          dataConverter: function (data) { return data; },
          language: 'html'
        }
      }
    },
    initialize: function () {
      var self = this;
      var p;
      p = this.options.parameters.html;
      console.log("Initialized Fuseki for element: ", this.el);
      var html_length;
      html_length = 0;
      var update = function () { // define the update function
        jQuery.ajax({
          url: "fuseki/status",
          type: 'GET',
          contentType: p.contentType,
          dataType: p.dataType,
          success: function (response) {
            var html = jQuery(response);
            // console.log('html:', html); // log the HTML to the console for debugging
            if (html.length) {
              if (html.length !== html_length) {
                self.el.html(html); // update the HTML if there are changes
                console.log("Fuseki: status updated");
                html_length = html.length;
              }
            } else {
              console.log('Error: #ajax-status element not found');
            }
          },
          error: function (xhr, status, error) {
            console.log('Error:', error);
          }
        };
      update(); // call the update function immediately after initialization
      var updateInterval = setInterval(update, 20000); // set the interval to 20 seconds (20000 milliseconds)
    }
  };
});
