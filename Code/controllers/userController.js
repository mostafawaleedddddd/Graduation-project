// Importing Database Models of Users
const users = require('../Models/user');
// Importing Modules
const path = require('path');

function login(req, res) {
    var query = { EmailAddress: req.body.Email, Password: req.body.Password };
    let usersPromise = users.findOne(query);

    Promise.all([usersPromise])
      .then(results => {
        let userResult = results[0];

        if (userResult != null) {
          req.session.user = userResult;
          req.session.role = userResult.role;
          res.redirect('/user');
        } else {
          res.status(401).send('Invalid credentials');
        }
      })
      .catch(err => {
        console.log(err);
        res.status(500).send('Internal server error');
      });
  };
async function addUser(req,res){
try{
  let Full_name=req.body.fullName;
  let email=req.body.email;
  const query={EmailAddress:email,Name:Full_name} 
  let user = await users.findOne(query);
  if(user){
    res.json({message:"User already exists"});
  }  
  else{
    let password=req.body.password;
    let email=req.body.email;
    let user = new users({
            Name: Full_name,
            EmailAddress: email,
            Password: password
    });
    await user.save()
        .then(()=>{
            res.redirect('/user/login');
        })
  }
}
catch(error){
  console.error(error);  // Log the error for debugging
  res.status(500).json({ message: "Internal server error" });
}
}
async function checkCredentials(req,res){
  var query = { EmailAddress: req.body.Email, Password: req.body.Password };
  var found=false;
  await users.find(query)
  .then(result=>{
      if(result.length>0){
          found=true;
      }
  })
  .catch(err=>{
      console.log(err);
  });
  if(found){
      res.send('Success');
  }else{
      res.send('Fail');
  }
}
module.exports = {
  login,
  checkCredentials,
  addUser
};