exports.home = (req, res) => {
  res.render("index");
};
exports.login = (req, res) => {
  res.render("authentication");
};

exports.signup = (req, res) => {
  res.render("authentication");
};